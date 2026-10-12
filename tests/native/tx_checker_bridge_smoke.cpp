// 测试专用 open-array adapter；验证 CPython bridge，不模拟 VCS 的调度或实际 ABI。
#include "../../sim/vcs/ble_python_dpi.h"

#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

struct RealArray {
    std::vector<double> values;
    int left = 0;
    int step = 1;
};

extern "C" int svDimensions(const svOpenArrayHandle) { return 1; }
extern "C" int svSize(const svOpenArrayHandle handle, int) {
    return static_cast<int>(static_cast<RealArray*>(handle)->values.size());
}
extern "C" int svLeft(const svOpenArrayHandle handle, int) {
    return static_cast<RealArray*>(handle)->left;
}
extern "C" int svRight(const svOpenArrayHandle handle, int) {
    auto* array = static_cast<RealArray*>(handle);
    return array->left + (static_cast<int>(array->values.size()) - 1) * array->step;
}
extern "C" void* svGetArrElemPtr1(const svOpenArrayHandle handle, int index) {
    auto* array = static_cast<RealArray*>(handle);
    const int offset = (index - array->left) / array->step;
    if (offset < 0 || offset >= static_cast<int>(array->values.size())) return nullptr;
    return &array->values[offset];
}

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

std::string read_packet(const std::string& directory, const std::string& name,
                        RealArray& i_data, RealArray& q_data) {
    std::ifstream iq(directory + "/" + name + ".txt");
    double i_value, q_value;
    i_data.values.clear();
    q_data.values.clear();
    while (iq >> i_value >> q_value) {
        i_data.values.push_back(i_value);
        q_data.values.push_back(q_value);
    }
    require(!i_data.values.empty(), "Missing native smoke IQ fixture");
    const std::string pdu_name = name == "bad_crc" ? "packet" :
        (name == "bad_crc_s2" ? "packet_s2" : (name == "bad_crc_s8" ? "packet_s8" : name));
    std::ifstream expected(directory + "/" + pdu_name + "_pdu.hex");
    std::string pdu;
    expected >> pdu;
    require(!pdu.empty(), "Missing native smoke PDU fixture");
    return pdu;
}

int main(int argc, char** argv) {
    try {
        require(argc == 5, "Usage: bridge_smoke PYTHON MODULE_ROOT SITE_PACKAGES FIXTURE_DIR");
        const char* message = nullptr;
        require(ble_python_init(argv[1], argv[2], argv[3], &message) == 0,
                message ? message : "Initialization failed");
        require(ble_python_init(argv[1], argv[2], argv[3], &message) == 0,
                "Repeated initialization failed");
        RealArray i_data, q_data;
        std::string expected = read_packet(argv[4], "packet", i_data, q_data);
        int passed, sync, crc, matched;
        int status = ble_python_check(&i_data, &q_data, 96e6, 1, 0x71764129, 32, 0,
            0x555555, expected.c_str(), "", &passed, &sync, &crc, &matched, &message);
        require(status == 0 && passed && sync && crc && matched,
                message ? message : "Valid packet failed");

        // 非零下标和降序下标验证 bridge 没有误用连续存储或默认 0 起始。
        i_data.left = 17;
        q_data.left = static_cast<int>(q_data.values.size()) + 23;
        q_data.step = -1;
        status = ble_python_check(&i_data, &q_data, 96e6, 1, 0x71764129, 32, 0,
            0x555555, expected.c_str(), "", &passed, &sync, &crc, &matched, &message);
        require(status == 0 && passed, "Open-array indexing failed");

        std::string wrong = expected;
        wrong.back() = wrong.back() == '0' ? '1' : '0';
        status = ble_python_check(&i_data, &q_data, 96e6, 1, 0x71764129, 32, 0,
            0x555555, wrong.c_str(), "", &passed, &sync, &crc, &matched, &message);
        require(status == 0 && !passed && sync && crc && !matched, "PDU mismatch passed");

        expected = read_packet(argv[4], "bad_crc", i_data, q_data);
        status = ble_python_check(&i_data, &q_data, 96e6, 1, 0x71764129, 32, 0,
            0x555555, expected.c_str(), "", &passed, &sync, &crc, &matched, &message);
        require(status == 0 && !passed && sync && !crc && matched, "Bad CRC passed");

        status = ble_python_check(&i_data, &q_data, 96e6, 1, 0x71764129, 32, 0,
            0x555555, "not_hex", "", &passed, &sync, &crc, &matched, &message);
        require(status != 0 && !passed && !sync && !crc && !matched, "Python exception passed");
        require(message && std::string(message).find("Traceback") != std::string::npos,
                "Python traceback was lost");

        // 异常后的正确调用仍需成功，验证 GIL 和异常状态清理。
        expected = read_packet(argv[4], "packet", i_data, q_data);
        status = ble_python_check(&i_data, &q_data, 96e6, 1, 0x71764129, 32, 0,
            0x555555, expected.c_str(), "", &passed, &sync, &crc, &matched, &message);
        require(status == 0 && passed, "Call after Python exception failed");
        expected = read_packet(argv[4], "packet2", i_data, q_data);
        status = ble_python_check(&i_data, &q_data, 96e6, 2, 0x71764129, 32, 1,
            0xC4C181, expected.c_str(), "", &passed, &sync, &crc, &matched, &message);
        require(status == 0 && passed && sync && crc && matched,
                "Second packet with different PHY/whitening/CRCInit failed");
        for (const int phy : {4, 3}) {
            const std::string suffix = phy == 4 ? "s2" : "s8";
            expected = read_packet(argv[4], "packet_" + suffix, i_data, q_data);
            status = ble_python_check(&i_data, &q_data, 96e6, phy, 0x71764129, 32, 0,
                0x555555, expected.c_str(), "", &passed, &sync, &crc, &matched, &message);
            require(status == 0 && passed && sync && crc && matched, "Valid Coded packet failed");
            wrong = expected;
            wrong.back() = wrong.back() == '0' ? '1' : '0';
            status = ble_python_check(&i_data, &q_data, 96e6, phy, 0x71764129, 32, 0,
                0x555555, wrong.c_str(), "", &passed, &sync, &crc, &matched, &message);
            require(status == 0 && !passed && sync && crc && !matched, "Coded PDU mismatch passed");
            status = ble_python_check(&i_data, &q_data, 96e6, phy == 4 ? 3 : 4, 0x71764129, 32, 0,
                0x555555, expected.c_str(), "", &passed, &sync, &crc, &matched, &message);
            require(status == 0 && !passed && sync && !crc && !matched && message &&
                std::string(message).find("PHY_CI_MISMATCH") == 0, "Coded CI mismatch passed");
            expected = read_packet(argv[4], "bad_crc_" + suffix, i_data, q_data);
            status = ble_python_check(&i_data, &q_data, 96e6, phy, 0x71764129, 32, 0,
                0x555555, expected.c_str(), "", &passed, &sync, &crc, &matched, &message);
            require(status == 0 && !passed && sync && !crc && matched, "Coded bad CRC passed");
        }
        // 不同 Coded 调用之后再次检查 uncoded，不能遗留 PHY/FEC 状态。
        expected = read_packet(argv[4], "packet", i_data, q_data);
        status = ble_python_check(&i_data, &q_data, 96e6, 1, 0x71764129, 32, 0,
            0x555555, expected.c_str(), "", &passed, &sync, &crc, &matched, &message);
        require(status == 0 && passed && sync && crc && matched, "Uncoded call after Coded failed");
        std::cout << "NATIVE_BRIDGE_SMOKE_PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
