module ble_tx_monitor #(
    parameter real SAMPLE_RATE_HZ = 96.0e6,
    // 覆盖 96 MHz、255-byte S8 的 1635840 samples，同时保持有界捕获。
    parameter int unsigned MAX_SAMPLES = 2097152,
    parameter bit FAIL_FATAL = 1'b1,
    parameter string REPORT_DIR = "",
    parameter time SAMPLE_SKEW = 0ps
) (
    input logic dac_clk,
    input logic dac_rstn,
    input logic tx_dfe_en,
    input real dac_i,
    input real dac_q,
    input int phy_mode,
    input int unsigned access_address,
    input int channel,
    input logic whitening,
    input int unsigned crc_init,
    input string expected_pdu_hex,
    output bit packet_checked,
    output bit packet_passed,
    output bit sync_found,
    output bit crc_valid,
    output bit pdu_match,
    output bit bridge_error,
    output int unsigned packet_count,
    output int unsigned failure_count,
    output int unsigned sample_count,
    output string check_message
);
    timeunit 1ns;
    timeprecision 1ps;

    import ble_python_dpi_pkg::*;

    real i_queue[$];
    real q_queue[$];
    bit capturing;
    bit discard_until_idle;
    bit reset_pending;
    int packet_phy;
    int unsigned packet_aa;
    int packet_channel;
    int packet_whitening;
    int unsigned packet_crc;
    string packet_expected;

    // #0 在 Observed region 采样 NBA 后的输出；非零 skew 表示边沿前采样。
    clocking capture_cb @(posedge dac_clk);
        default input #SAMPLE_SKEW;
        input dac_rstn, tx_dfe_en, dac_i, dac_q;
        input phy_mode, access_address, channel, whitening, crc_init, expected_pdu_hex;
    endclocking

    initial begin : initialize_bridge
        string python_executable;
        string module_root;
        string site_packages;
        string message;
        int status;
        packet_checked = 1'b0;
        packet_passed = 1'b0;
        sync_found = 1'b0;
        crc_valid = 1'b0;
        pdu_match = 1'b0;
        bridge_error = 1'b0;
        packet_count = 0;
        failure_count = 0;
        sample_count = 0;
        check_message = "";
        if (!$value$plusargs("BLE_PYTHON=%s", python_executable) ||
            !$value$plusargs("BLE_MODULE_ROOT=%s", module_root)) begin
            $fatal(1, "BLE_PYTHON and BLE_MODULE_ROOT plusargs are required");
        end
        if (!$value$plusargs("BLE_SITE_PACKAGES=%s", site_packages)) begin
            site_packages = "";
        end
        status = ble_python_init(python_executable, module_root, site_packages, message);
        if (status != 0) begin
            $fatal(1, "Python bridge initialization failed: %s", message);
        end
        $display("[BLE-TX] %s", message);
    end

    // 即使复位脉冲完全位于两个采样边沿之间，也不能把被打断的包判为通过。
    always @(negedge dac_rstn) begin
        reset_pending = 1'b1;
    end

    task automatic capture_failure(input string reason);
        sample_count = i_queue.size();
        packet_count++;
        failure_count++;
        packet_checked = 1'b1;
        packet_passed = 1'b0;
        sync_found = 1'b0;
        crc_valid = 1'b0;
        pdu_match = 1'b0;
        bridge_error = 1'b0;
        check_message = reason;
        capturing = 1'b0;
        discard_until_idle = 1'b1;
        i_queue.delete();
        q_queue.delete();
        $display("[BLE-TX] packet=%0d samples=%0d FAIL %s", packet_count, sample_count, reason);
        if (FAIL_FATAL) begin
            $fatal(1, "BLE TX capture failed: %s", reason);
        end
    endtask

    task automatic decode_packet();
        real i_samples[];
        real q_samples[];
        int status;
        int passed_value;
        int sync_value;
        int crc_value;
        int match_value;
        string message;
        string report_path;
        sample_count = i_queue.size();
        i_samples = new[sample_count];
        q_samples = new[sample_count];
        foreach (i_samples[index]) begin
            i_samples[index] = i_queue[index];
            q_samples[index] = q_queue[index];
        end
        report_path = REPORT_DIR == "" ? "" :
            $sformatf("%s/%m_packet_%06d.json", REPORT_DIR, packet_count + 1);
        status = ble_python_check(
            i_samples, q_samples, SAMPLE_RATE_HZ, packet_phy, packet_aa,
            packet_channel, packet_whitening, packet_crc, packet_expected, report_path,
            passed_value, sync_value, crc_value, match_value, message
        );
        packet_count++;
        packet_checked = 1'b1;
        packet_passed = status == 0 && passed_value == 1;
        sync_found = status == 0 && sync_value == 1;
        crc_valid = status == 0 && crc_value == 1;
        pdu_match = status == 0 && match_value == 1;
        bridge_error = status != 0;
        check_message = message;
        capturing = 1'b0;
        i_queue.delete();
        q_queue.delete();
        if (!packet_passed) begin
            failure_count++;
        end
        $display("[BLE-TX] packet=%0d samples=%0d %s", packet_count, sample_count, message);
        if (!packet_passed && FAIL_FATAL) begin
            $fatal(1, "BLE TX check failed: %s", message);
        end
    endtask

    always @(capture_cb) begin
        packet_checked = 1'b0;
        if (reset_pending || capture_cb.dac_rstn !== 1'b1) begin
            if (capturing) begin
                capture_failure("RESET_DURING_PACKET");
            end
            reset_pending = 1'b0;
        end else if ($isunknown(capture_cb.tx_dfe_en)) begin
            if (!discard_until_idle) begin
                capture_failure("UNKNOWN_TX_DFE_EN");
            end
        end else if (!capture_cb.tx_dfe_en) begin
            if (capturing) begin
                decode_packet();
            end
            discard_until_idle = 1'b0;
        end else if (!discard_until_idle) begin
            if (!capturing) begin
                if ($isunknown({capture_cb.phy_mode, capture_cb.access_address,
                    capture_cb.channel, capture_cb.whitening, capture_cb.crc_init})) begin
                    capture_failure("UNKNOWN_PACKET_CONFIG");
                end else begin
                    i_queue.delete();
                    q_queue.delete();
                    packet_phy = capture_cb.phy_mode;
                    packet_aa = capture_cb.access_address;
                    packet_channel = capture_cb.channel;
                    packet_whitening = int'(capture_cb.whitening);
                    packet_crc = capture_cb.crc_init;
                    packet_expected = capture_cb.expected_pdu_hex;
                    capturing = 1'b1;
                end
            end
            if (capturing) begin
                if (i_queue.size() >= MAX_SAMPLES) begin
                    capture_failure("MAX_SAMPLES_EXCEEDED");
                end else begin
                    i_queue.push_back(capture_cb.dac_i);
                    q_queue.push_back(capture_cb.dac_q);
                end
            end
        end
    end

    // testcase 必须在最后的 idle 采样完成后调用，避免零包或未闭合包默认 PASS。
    task automatic check_complete(input int unsigned expected_packets);
        if (capturing || discard_until_idle || reset_pending) begin
            $fatal(1, "BLE TX capture unfinished or interrupted");
        end
        if (expected_packets == 0 || packet_count != expected_packets || failure_count != 0) begin
            $fatal(1, "BLE TX summary failed: expected=%0d checked=%0d failures=%0d",
                expected_packets, packet_count, failure_count);
        end
    endtask
endmodule
