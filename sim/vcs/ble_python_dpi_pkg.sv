package ble_python_dpi_pkg;
    timeunit 1ns;
    timeprecision 1ps;

    // 与 BLEPhyMode 保持一致；不使用 SystemVerilog enum 的隐式序号。
    localparam int BLE_LE_1M = 1;
    localparam int BLE_LE_2M = 2;
    localparam int BLE_LE_CODED_S8 = 3;
    localparam int BLE_LE_CODED_S2 = 4;

    import "DPI-C" function int ble_python_init(
        input string python_executable,
        input string module_root,
        input string site_packages,
        output string message
    );

    // 返回值只表示 bridge 状态；正常解调但 CRC/PDU 错误仍返回 0，passed 为 0。
    import "DPI-C" function int ble_python_check(
        input real i_samples[],
        input real q_samples[],
        input real sample_rate,
        input int phy_mode,
        input int unsigned access_address,
        input int channel,
        input int whitening,
        input int unsigned crc_init,
        input string expected_pdu_hex,
        input string report_path,
        output int passed,
        output int sync_found,
        output int crc_valid,
        output int pdu_match,
        output string message
    );
endpackage
