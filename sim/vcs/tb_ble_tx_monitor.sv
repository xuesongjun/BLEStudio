module tb_ble_tx_monitor;
    timeunit 1ns;
    timeprecision 1ps;

    import ble_python_dpi_pkg::*;

    localparam real SAMPLE_RATE_HZ = 96.0e6;
    // 37-byte S8 为 296448 samples；卡高负例同步使用这个上限。
    localparam int MAX_SAMPLES = 327680;
    bit dac_clk;
    logic dac_rstn = 1'b0;
    logic tx_dfe_en;
    real dac_i;
    real dac_q;
    logic next_enable = 1'b0;
    real next_i = 0.0;
    real next_q = 0.0;
    int phy_mode = BLE_LE_1M;
    int unsigned access_address = 32'h71764129;
    int channel = 32;
    logic whitening = 1'b0;
    int unsigned crc_init = 32'h00555555;
    string expected_pdu_hex;
    string scenario;
    string fixture_dir;
    real i_values[$];
    real q_values[$];
    bit packet_checked;
    bit packet_passed;
    bit sync_found;
    bit crc_valid;
    bit pdu_match;
    bit bridge_error;
    int unsigned packet_count;
    int unsigned failure_count;
    int unsigned sample_count;
    string check_message;

    // 1 ps 时间精度下半周期有舍入；协议采样率始终显式传递为 96 MHz。
    initial begin
        dac_clk = 1'b0;
        forever #(0.5e9 / SAMPLE_RATE_HZ) dac_clk = ~dac_clk;
    end

    always @(posedge dac_clk) begin
        tx_dfe_en <= next_enable;
        dac_i <= next_i;
        dac_q <= next_q;
    end

    ble_tx_monitor #(
        .SAMPLE_RATE_HZ(SAMPLE_RATE_HZ), .MAX_SAMPLES(MAX_SAMPLES),
        .FAIL_FATAL(1'b0), .REPORT_DIR("reports")
    ) monitor (
        .dac_clk(dac_clk), .dac_rstn(dac_rstn), .tx_dfe_en(tx_dfe_en),
        .dac_i(dac_i), .dac_q(dac_q), .phy_mode(phy_mode),
        .access_address(access_address), .channel(channel), .whitening(whitening),
        .crc_init(crc_init), .expected_pdu_hex(expected_pdu_hex),
        .packet_checked(packet_checked), .packet_passed(packet_passed),
        .sync_found(sync_found), .crc_valid(crc_valid), .pdu_match(pdu_match),
        .bridge_error(bridge_error), .packet_count(packet_count),
        .failure_count(failure_count), .sample_count(sample_count),
        .check_message(check_message)
    );

    task automatic read_fixture(input string name);
        int file_handle;
        int read_count;
        real i_value;
        real q_value;
        i_values.delete();
        q_values.delete();
        file_handle = $fopen({fixture_dir, "/", name, ".txt"}, "r");
        if (file_handle == 0) begin
            $fatal(1, "Cannot open IQ fixture %s", name);
        end
        while (!$feof(file_handle)) begin
            read_count = $fscanf(file_handle, "%f %f", i_value, q_value);
            if (read_count == 2) begin
                i_values.push_back(i_value);
                q_values.push_back(q_value);
            end else if (!$feof(file_handle)) begin
                $fatal(1, "Malformed IQ fixture %s", name);
            end
        end
        $fclose(file_handle);
        if (i_values.size() == 0) begin
            $fatal(1, "Empty IQ fixture");
        end
    endtask

    task automatic read_expected(input string name);
        int file_handle;
        int read_count;
        file_handle = $fopen({fixture_dir, "/", name, "_pdu.hex"}, "r");
        if (file_handle == 0) begin
            $fatal(1, "Cannot open expected PDU fixture %s", name);
        end
        read_count = $fscanf(file_handle, "%s", expected_pdu_hex);
        $fclose(file_handle);
        if (read_count != 1) begin
            $fatal(1, "Missing expected PDU");
        end
    endtask

    // 在 posedge 用 NBA 更新 DAC，验证 monitor #0 不会漏掉首/末样点。
    task automatic drive_samples(input int count);
        for (int index = 0; index < count; index++) begin
            next_enable = 1'b1;
            next_i = i_values[index % i_values.size()];
            next_q = q_values[index % q_values.size()];
            @(negedge dac_clk);
        end
    endtask

    task automatic drive_idle();
        next_enable = 1'b0;
        next_i = 0.0;
        next_q = 0.0;
        @(negedge dac_clk);
    endtask

    task automatic assert_result(
        input int expected_count, input bit passed, input bit sync,
        input bit crc, input bit matched, input bit bridge
    );
        if (!packet_checked || packet_count != expected_count ||
            packet_passed != passed || sync_found != sync ||
            crc_valid != crc || pdu_match != matched || bridge_error != bridge) begin
            $fatal(1, "Unexpected checker result: count=%0d passed=%0b sync=%0b crc=%0b match=%0b bridge=%0b %s",
                packet_count, packet_passed, sync_found,
                crc_valid, pdu_match, bridge_error, check_message);
        end
    endtask

    initial begin : run_scenario
        if (!$value$plusargs("SCENARIO=%s", scenario)) begin
            scenario = "good";
        end
        if (!$value$plusargs("FIXTURE_DIR=%s", fixture_dir)) begin
            $fatal(1, "FIXTURE_DIR is required");
        end
        case (scenario)
            "coded_s2", "coded_s2_mismatch", "coded_s2_crc", "coded_ci_mismatch", "coded_modes": begin
                phy_mode = BLE_LE_CODED_S2;
                read_fixture(scenario == "coded_s2_crc" ? "bad_crc_s2" : "packet_s2");
                read_expected("packet_s2");
            end
            "coded_s8", "coded_s8_mismatch", "coded_s8_crc": begin
                phy_mode = BLE_LE_CODED_S8;
                read_fixture(scenario == "coded_s8_crc" ? "bad_crc_s8" : "packet_s8");
                read_expected("packet_s8");
            end
            default: begin
                read_fixture(scenario == "crc" ? "bad_crc" : "packet");
                read_expected("packet");
            end
        endcase
        repeat (3) @(negedge dac_clk);
        dac_rstn = 1'b1;
        drive_idle();

        case (scenario)
            "good", "two_packets", "mismatch", "crc", "bridge_error", "init_error",
            "coded_s2", "coded_s8", "coded_s2_mismatch", "coded_s8_mismatch",
            "coded_s2_crc", "coded_s8_crc", "coded_ci_mismatch", "coded_modes": begin
                if (scenario == "mismatch" || scenario == "coded_s2_mismatch" || scenario == "coded_s8_mismatch") begin
                    expected_pdu_hex.putc(expected_pdu_hex.len() - 1,
                        expected_pdu_hex.getc(expected_pdu_hex.len() - 1) == "0" ? "1" : "0");
                end
                if (scenario == "bridge_error") begin
                    expected_pdu_hex = "invalid_hex";
                end
                if (scenario == "coded_ci_mismatch") begin
                    phy_mode = BLE_LE_CODED_S8;
                end
                drive_samples(i_values.size());
                drive_idle();
                if (sample_count != i_values.size()) begin
                    $fatal(1, "Lost or duplicated DAC samples");
                end
                if (scenario == "mismatch" || scenario == "coded_s2_mismatch" || scenario == "coded_s8_mismatch") begin
                    assert_result(1, 0, 1, 1, 0, 0);
                end else if (scenario == "crc" || scenario == "coded_s2_crc" || scenario == "coded_s8_crc") begin
                    assert_result(1, 0, 1, 0, 1, 0);
                end else if (scenario == "coded_ci_mismatch") begin
                    assert_result(1, 0, 1, 0, 0, 0);
                    if (check_message.substr(0, 14) != "PHY_CI_MISMATCH") begin
                        $fatal(1, "PHY/CI mismatch was not reported");
                    end
                end else if (scenario == "bridge_error") begin
                    assert_result(1, 0, 0, 0, 0, 1);
                    $display("[SMOKE] NEGATIVE_CASE_CONFIRMED bridge_error");
                    $fatal(1, "Expected Python configuration failure");
                end else begin
                    assert_result(1, 1, 1, 1, 1, 0);
                    if (scenario == "two_packets") begin
                        read_fixture("packet2");
                        read_expected("packet2");
                        phy_mode = BLE_LE_2M;
                        whitening = 1'b1;
                        crc_init = 32'h00C4C181;
                        drive_samples(i_values.size());
                        drive_idle();
                        assert_result(2, 1, 1, 1, 1, 0);
                        if (sample_count != i_values.size()) begin
                            $fatal(1, "Second packet sample count mismatch");
                        end
                    end
                    if (scenario == "coded_modes") begin
                        read_fixture("packet_s8");
                        read_expected("packet_s8");
                        phy_mode = BLE_LE_CODED_S8;
                        drive_samples(i_values.size());
                        drive_idle();
                        assert_result(2, 1, 1, 1, 1, 0);
                        if (sample_count != i_values.size()) begin
                            $fatal(1, "S8 packet sample count mismatch");
                        end
                        read_fixture("packet");
                        read_expected("packet");
                        phy_mode = BLE_LE_1M;
                        drive_samples(i_values.size());
                        drive_idle();
                        assert_result(3, 1, 1, 1, 1, 0);
                        read_fixture("packet2");
                        read_expected("packet2");
                        phy_mode = BLE_LE_2M;
                        whitening = 1'b1;
                        crc_init = 32'h00C4C181;
                        drive_samples(i_values.size());
                        drive_idle();
                        assert_result(4, 1, 1, 1, 1, 0);
                    end
                    monitor.check_complete(scenario == "coded_modes" ? 4 : (scenario == "two_packets" ? 2 : 1));
                end
            end
            "reset": begin
                drive_samples(64);
                // 复位脉冲不跨越采样边沿，验证 reset_pending 不会漏检。
                #1ns dac_rstn = 1'b0;
                #1ns dac_rstn = 1'b1;
                @(negedge dac_clk);
                assert_result(1, 0, 0, 0, 0, 0);
                if (check_message != "RESET_DURING_PACKET") begin
                    $fatal(1, "Reset interruption not reported");
                end
                drive_idle();
                drive_samples(i_values.size());
                drive_idle();
                assert_result(2, 1, 1, 1, 1, 0);
                if (failure_count != 1) begin
                    $fatal(1, "Reset erased failure history");
                end
            end
            "unknown": begin
                next_enable = 1'bx;
                @(negedge dac_clk);
                assert_result(1, 0, 0, 0, 0, 0);
                if (check_message != "UNKNOWN_TX_DFE_EN") begin
                    $fatal(1, "Unknown enable not reported");
                end
                drive_idle();
            end
            "missing": begin
                $display("[SMOKE] NEGATIVE_CASE_CONFIRMED missing");
                monitor.check_complete(1);
                $display("[SMOKE] UNEXPECTED_ACCEPT missing");
                $finish;
            end
            "unfinished": begin
                drive_samples(64);
                $display("[SMOKE] NEGATIVE_CASE_CONFIRMED unfinished");
                monitor.check_complete(1);
                $display("[SMOKE] UNEXPECTED_ACCEPT unfinished");
                $finish;
            end
            "stuck": begin
                drive_samples(MAX_SAMPLES + 1);
                assert_result(1, 0, 0, 0, 0, 0);
                if (check_message != "MAX_SAMPLES_EXCEEDED") begin
                    $fatal(1, "Capture limit was not enforced");
                end
                $display("[SMOKE] NEGATIVE_CASE_CONFIRMED stuck");
                monitor.check_complete(1);
                $display("[SMOKE] UNEXPECTED_ACCEPT stuck");
                $finish;
            end
            default: $fatal(1, "Unknown smoke scenario: %s", scenario);
        endcase
        $display("[SMOKE] PASS %s", scenario);
        $finish;
    end

    initial begin : watchdog
        #10ms;
        $fatal(1, "Smoke simulation timeout");
    end
endmodule
