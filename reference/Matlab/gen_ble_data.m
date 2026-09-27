%% 生成 BLE DTM 测试波形
% 本脚本以 Bluetooth Core DTM 的 transmission order 为唯一规范来源。
% clean、ADC resampled 和 AWGN 输出分别保存，避免不同采样率/状态互相覆盖。

%% 用户配置（保留旧变量名，便于已有工作流迁移）
Fs = 96e6;
rate = 0;                         % 0: LE1M, 1: LE2M, 2: LE125K, 3: LE500K
chanIdx = 32;                     % LE channel index 0..39
gensimtxt = 1;                    % 是否生成 packed IQ TXT
iSPaddZero = 0;                   % 是否按 DTM packet interval I(L) 补零
isResample = 0;                   % 是否额外生成模拟 ADC 采样文件
useAWGN = 0;                      % 是否生成带噪 IQ 文件
Amp = 1;                          % IQ amplitude scale
awgnSnrDb = 5;                    % AWGN active-packet SNR (dB)
awgnSeed = 1;                     % AWGN deterministic seed
enablePlots = 1;                  % 是否显示时域/眼图/星座图
validateIdealRx = 1;              % 是否执行 clean ideal RX 自检

%% BLE/DTM 参数
accessAddressValue = hex2dec('71764129');
crcInitValue = hex2dec('555555');
headerValue = 0;                  % DTM payload type: 0..7
payloadLenBytes = 37;             % DTM payload length: 0..255
modulationIndex = 0.5;
pulseLength = 1;
crcPolynomial = 'z^24+z^10+z^9+z^6+z^4+z^3+z+1';
resampleTolerance = 1e-12;

validateattributes(Fs, {'numeric'}, {'real', 'finite', 'scalar', 'positive'}, ...
    mfilename, 'Fs');
validateattributes(rate, {'numeric'}, {'real', 'finite', 'scalar', 'integer', '>=', 0, '<=', 3}, ...
    mfilename, 'rate');
validateattributes(chanIdx, {'numeric'}, {'real', 'finite', 'scalar', 'integer', '>=', 0, '<=', 39}, ...
    mfilename, 'chanIdx');
validateattributes(accessAddressValue, {'numeric'}, {'real', 'finite', 'scalar', 'integer', '>=', 0, '<', 2^32}, ...
    mfilename, 'accessAddressValue');
validateattributes(crcInitValue, {'numeric'}, {'real', 'finite', 'scalar', 'integer', '>=', 0, '<', 2^24}, ...
    mfilename, 'crcInitValue');
validateattributes(headerValue, {'numeric'}, {'real', 'finite', 'scalar', 'integer', '>=', 0, '<=', 7}, ...
    mfilename, 'headerValue');
validateattributes(payloadLenBytes, {'numeric'}, {'real', 'finite', 'scalar', 'integer', '>=', 0, '<=', 255}, ...
    mfilename, 'payloadLenBytes');
validateattributes(Amp, {'numeric'}, {'real', 'finite', 'scalar', 'positive'}, ...
    mfilename, 'Amp');
validateattributes(awgnSnrDb, {'numeric'}, {'real', 'finite', 'scalar'}, ...
    mfilename, 'awgnSnrDb');
validateattributes(awgnSeed, {'numeric'}, ...
    {'real', 'finite', 'scalar', 'integer', '>=', 0, '<=', 2^32 - 1}, ...
    mfilename, 'awgnSeed');
gensimtxt = validate_flag(gensimtxt, 'gensimtxt');
iSPaddZero = validate_flag(iSPaddZero, 'iSPaddZero');
isResample = validate_flag(isResample, 'isResample');
useAWGN = validate_flag(useAWGN, 'useAWGN');
enablePlots = validate_flag(enablePlots, 'enablePlots');
validateIdealRx = validate_flag(validateIdealRx, 'validateIdealRx');

switch rate
    case 0
        phyMode = 'LE1M';
        symbolRate = 1e6;
    case 1
        phyMode = 'LE2M';
        symbolRate = 2e6;
    case 2
        phyMode = 'LE125K';
        symbolRate = 1e6;
    case 3
        phyMode = 'LE500K';
        symbolRate = 1e6;
    otherwise
        error('BLEStudio:gen_ble_data:InvalidRate', 'rate must be one of 0, 1, 2, or 3.');
end

% SamplesPerSymbol 必须是整数；不能用 round 静默改变实际采样率。
spsExact = Fs / symbolRate;
if isnan(spsExact) || isinf(spsExact) || spsExact < 1 || ...
        abs(spsExact - round(spsExact)) > 1e-12
    error('BLEStudio:gen_ble_data:InvalidSamplesPerSymbol', ...
        'Fs/symbolRate must be a positive integer. Fs=%.17g, symbolRate=%.17g.', ...
        Fs, symbolRate);
end
sps = round(spsExact);

%% 路径和 helper 环境
scriptPath = mfilename('fullpath');
if isempty(scriptPath)
    scriptDir = pwd;
else
    scriptDir = fileparts(scriptPath);
end
outputDir = fullfile(scriptDir, '..', 'BLE_PKT');
if ~exist(outputDir, 'dir')
    [mkdirOk, mkdirMsg] = mkdir(outputDir);
    if ~mkdirOk
        error('BLEStudio:gen_ble_data:CreateOutputDir', ...
            'Cannot create output directory "%s": %s', outputDir, mkdirMsg);
    end
end
% 从任意 CWD 运行脚本时，确保同目录 helper 优先于 MATLAB path 上的旧副本。
% 这两个 helper 属于本 reference vector 的格式契约，不能静默解析到其他版本。
addpath(scriptDir, '-begin');

%% 生成 DTM Payload
payloadBits = generate_dtm_payload(headerValue, payloadLenBytes);
payloadBits = double(payloadBits(:));

% Core DTM PRBS9 的可观察前缀是 transmission-order golden vector。
if headerValue == 0 && numel(payloadBits) >= 20
    expectedPrbs9Prefix = [1 1 1 1 1 1 1 1 1 0 0 0 0 0 1 1 1 1 0 1]';
    assert(isequal(payloadBits(1:20), expectedPrbs9Prefix), ...
        'BLEStudio:gen_ble_data:Prbs9Vector', ...
        'Generated PRBS9 does not match the BLE Core DTM transmission-order vector.');
elseif headerValue == 3 && numel(payloadBits) >= 20
    expectedPrbs15Prefix = [1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 0 0 0 0 0]';
    assert(isequal(payloadBits(1:20), expectedPrbs15Prefix), ...
        'BLEStudio:gen_ble_data:Prbs15Vector', ...
        'Generated PRBS15 does not match the BLE Core DTM transmission-order vector.');
end
if payloadLenBytes == 37 && headerValue == 0
    expectedPrbs9Hex = ...
        'ffc1fbe84c90728be7b3518963ab232302841872aa612f3b51a8e53749fbc9ca0c18532cfd';
    assert(strcmp(bits_lsb_to_hex(payloadBits), expectedPrbs9Hex), ...
        'BLEStudio:gen_ble_data:Prbs9FullVector', ...
        'Generated 37-byte PRBS9 does not match the BLE Core DTM vector.');
elseif payloadLenBytes == 37 && headerValue == 3
    expectedPrbs15Hex = ...
        'ff7f00200018000a800720029801aa807f202018180a8a8727229a99ab2aff5f0038001280';
    assert(strcmp(bits_lsb_to_hex(payloadBits), expectedPrbs15Hex), ...
        'BLEStudio:gen_ble_data:Prbs15FullVector', ...
        'Generated 37-byte PRBS15 does not match the BLE Core DTM vector.');
end

headerBits = int_to_lsb_bits(headerValue, 8);
lengthBits = int_to_lsb_bits(payloadLenBytes, 8);
pdu = double([headerBits; lengthBits; payloadBits]);
pduCRC = generate_ble_crc(pdu, crcInitValue, crcPolynomial);

accessAddressBits = int_to_lsb_bits(accessAddressValue, 32);
rawWaveform = bleWaveformGenerator(pduCRC, ...
    'Mode', phyMode, ...
    'SamplesPerSymbol', sps, ...
    'ChannelIndex', chanIdx, ...
    'AccessAddress', accessAddressBits, ...
    'WhitenStatus', 'Off', ...
    'ModulationIndex', modulationIndex, ...
    'PulseLength', pulseLength);
rawWaveform = Amp * rawWaveform(:);
packetDurationUs = numel(rawWaveform) / Fs * 1e6;
activeSignalPower = mean(abs(rawWaveform).^2);

packetInfo = struct();
packetInfo.pdu = pdu;
packetInfo.pdu_crc = pduCRC;
packetInfo.payload_bits = payloadBits;
packetInfo.access_address_bits = accessAddressBits;
packetInfo.payload_hex = bits_lsb_to_hex(payloadBits);
packetInfo.pdu_hex = bits_lsb_to_hex(pdu);
packetInfo.pdu_with_crc_hex = bits_lsb_to_hex(pduCRC);
packetInfo.crc_polynomial = crcPolynomial;

% 在原始采样率下应用 packet interval；padding 只追加 complex zero。
[nativeWaveform, nativeInterval] = apply_packet_interval( ...
    rawWaveform, Fs, packetDurationUs, iSPaddZero);
nativeMetadata = make_metadata( ...
    'clean_tx', phyMode, Fs, Fs, sps, chanIdx, accessAddressValue, ...
    headerValue, payloadLenBytes, crcInitValue, packetDurationUs, ...
    nativeInterval, false, 1, 1, 0, false, awgnSnrDb, 0, ...
    modulationIndex, pulseLength, awgnSeed, Amp, activeSignalPower, packetInfo);
nativeStem = make_native_stem(phyMode, Fs, chanIdx, headerValue, ...
    payloadLenBytes, iSPaddZero);
save_waveform_bundle(outputDir, nativeStem, nativeWaveform, Fs, ...
    nativeMetadata, packetInfo, gensimtxt);

if enablePlots
    figure('Name', 'BLE clean waveform');
    plot(real(nativeWaveform));
    hold on;
    plot(imag(nativeWaveform));
    grid on;
    legend('I', 'Q');
    title(sprintf('%s clean IQ, %.6g Msps', phyMode, Fs / 1e6));
    if exist('eyediagram', 'file') == 2
        figure('Name', 'BLE clean eye diagram');
        eyediagram(rawWaveform, 2 * sps);
    end

    % Constellation Diagram 只显示 active packet，排除 packet interval padding zero。
    constel = comm.ConstellationDiagram('ColorFading', true, ...
        'ShowTrajectory', 1, ...
        'ShowReferenceConstellation', false);
    constel(rawWaveform);
    release(constel);
end

if validateIdealRx
    verify_ideal_rx(rawWaveform, Fs, phyMode, sps, chanIdx, ...
        modulationIndex, pulseLength, pduCRC, accessAddressBits, 0, true);
end

% AWGN 输出使用 active packet 的功率计算噪声，避免 padding zero 改变 SNR。
if useAWGN
    [noisyNative, nativeNoisePower] = add_awgn_active_power( ...
        nativeWaveform, nativeInterval.active_samples, awgnSnrDb, awgnSeed);
    noisyMetadata = make_metadata( ...
        'awgn_rx', phyMode, Fs, Fs, sps, chanIdx, accessAddressValue, ...
        headerValue, payloadLenBytes, crcInitValue, packetDurationUs, ...
        nativeInterval, false, 1, 1, 0, true, awgnSnrDb, nativeNoisePower, ...
        modulationIndex, pulseLength, awgnSeed, Amp, activeSignalPower, packetInfo);
    noisyStem = sprintf('%s_AWGN_%sdB', nativeStem, number_token(awgnSnrDb));
    save_waveform_bundle(outputDir, noisyStem, noisyNative, Fs, ...
        noisyMetadata, packetInfo, gensimtxt);
    if validateIdealRx
        verify_ideal_rx(noisyNative(1:nativeInterval.active_samples), Fs, phyMode, sps, ...
            chanIdx, modulationIndex, pulseLength, pduCRC, accessAddressBits, ...
            nativeNoisePower, false);
    end
end

%% 模拟 ADC 输出
if isResample
    adcClockHz = calculate_adc_clock(rate, chanIdx);
    [P, Q] = rat(adcClockHz / Fs, resampleTolerance);
    FsOut = Fs * P / Q;
    adcActive = resample(rawWaveform, P, Q);
    adcRawSamples = numel(adcActive);
    expectedPacketSamples = round(packetDurationUs * FsOut / 1e6);
    adcActive = fit_sample_count(adcActive, expectedPacketSamples);
    adcAdjustmentSamples = expectedPacketSamples - adcRawSamples;
    if abs(adcAdjustmentSamples) > 1
        error('BLEStudio:gen_ble_data:ResampleLengthAdjustment', ...
            'Resample length adjustment is %d samples; expected at most one.', ...
            adcAdjustmentSamples);
    end
    [adcWaveform, adcInterval] = apply_packet_interval( ...
        adcActive, FsOut, packetDurationUs, iSPaddZero);
    adcMetadata = make_metadata( ...
        'adc_clean', phyMode, Fs, FsOut, FsOut / symbolRate, chanIdx, ...
        accessAddressValue, headerValue, payloadLenBytes, crcInitValue, ...
        packetDurationUs, adcInterval, true, P, Q, adcClockHz, false, ...
        awgnSnrDb, 0, modulationIndex, pulseLength, awgnSeed, Amp, ...
        activeSignalPower, packetInfo);
    adcStem = sprintf('%s_ADC_%sMsps', nativeStem, rate_token(FsOut));
    adcMetadata.resample_raw_samples = adcRawSamples;
    adcMetadata.resample_adjustment_samples = adcAdjustmentSamples;
    adcMetadata.awgn_stage = 'not applicable';
    save_waveform_bundle(outputDir, adcStem, adcWaveform, FsOut, ...
        adcMetadata, packetInfo, gensimtxt);

    if useAWGN
        [noisyAdc, adcNoisePower] = add_awgn_active_power( ...
            adcWaveform, adcInterval.active_samples, awgnSnrDb, awgnSeed);
        noisyAdcMetadata = make_metadata( ...
            'adc_post_awgn', phyMode, Fs, FsOut, FsOut / symbolRate, ...
            chanIdx, accessAddressValue, headerValue, payloadLenBytes, ...
            crcInitValue, packetDurationUs, adcInterval, true, P, Q, ...
            adcClockHz, true, awgnSnrDb, adcNoisePower, ...
            modulationIndex, pulseLength, awgnSeed, Amp, activeSignalPower, packetInfo);
        noisyAdcStem = sprintf('%s_AWGN_%sdB', adcStem, number_token(awgnSnrDb));
        noisyAdcMetadata.resample_raw_samples = adcRawSamples;
        noisyAdcMetadata.resample_adjustment_samples = adcAdjustmentSamples;
        noisyAdcMetadata.awgn_stage = 'post_resample';
        save_waveform_bundle(outputDir, noisyAdcStem, noisyAdc, FsOut, ...
            noisyAdcMetadata, packetInfo, gensimtxt);
    end
end

fprintf('BLE waveform generation completed. Output directory: %s\n', outputDir);

%% Local functions

function bits = generate_dtm_payload(headerValue, payloadLenBytes)
    payloadBitsCount = payloadLenBytes * 8;
    % 固定 pattern 按 Core 定义的 transmission order 写出，而不是按十六进制
    % 文本的 MSB-first 显示顺序写出。按 LSB-first byte 打包时，type 1/6
    % 分别得到 0x0F/0xF0；这正是 transmission-order 命名与 byte 显示的差异。
    switch headerValue
        case 0
            bits = generate_core_prbs9(payloadBitsCount);
        case 1
            bits = repmat([1 1 1 1 0 0 0 0], 1, payloadLenBytes)';
        case 2
            bits = repmat([1 0 1 0 1 0 1 0], 1, payloadLenBytes)';
        case 3
            bits = generate_core_prbs15(payloadBitsCount);
        case 4
            bits = ones(payloadBitsCount, 1);
        case 5
            bits = zeros(payloadBitsCount, 1);
        case 6
            bits = repmat([0 0 0 0 1 1 1 1], 1, payloadLenBytes)';
        case 7
            bits = repmat([0 1 0 1 0 1 0 1], 1, payloadLenBytes)';
        otherwise
            error('BLEStudio:gen_ble_data:InvalidDtmHeader', ...
                'DTM header/payload type must be in the range 0..7.');
    end
    bits = double(bits(:));
end

function bits = generate_core_prbs9(numBits)
    % 数组采用镜像编号：state(1)=Core stage 9（输出），state(5)=stage 5。
    % 因此下面的 state(1) XOR state(5) 等价于 Core 图的 stage 9 XOR stage 5。
    state = true(1, 9);
    bits = false(numBits, 1);
    for index = 1:numBits
        bits(index) = state(1);
        feedback = xor(state(1), state(5));
        state(1:8) = state(2:9);
        state(9) = feedback;
    end
    bits = double(bits);
end

function bits = generate_core_prbs15(numBits)
    % 数组采用镜像编号：state(1)=Core stage 15（输出），state(2)=stage 14。
    % 因此下面的 state(1) XOR state(2) 等价于 Core 图的 stage 15 XOR stage 14。
    state = true(1, 15);
    bits = false(numBits, 1);
    for index = 1:numBits
        bits(index) = state(1);
        feedback = xor(state(1), state(2));
        state(1:14) = state(2:15);
        state(15) = feedback;
    end
    bits = double(bits);
end

function bits = int_to_lsb_bits(value, width)
    bits = zeros(width, 1);
    for index = 1:width
        bits(index) = bitget(value, index);
    end
end

function bits = int_to_msb_bits(value, width)
    bits = zeros(width, 1);
    for index = 1:width
        bits(index) = bitget(value, width - index + 1);
    end
end

function codeword = generate_ble_crc(dataBits, crcInitValue, polynomial)
    % CRC API 的 shift-register initial conditions 使用 MSB-first 行向量。
    initialConditions = int_to_msb_bits(crcInitValue, 24).';
    hasCrcConfig = exist('crcConfig', 'file') == 2 || ...
        exist('crcConfig', 'class') == 8;
    hasCrcGenerate = exist('crcGenerate', 'file') == 2 || ...
        exist('crcGenerate', 'builtin') == 5;
    if hasCrcConfig && hasCrcGenerate
        crcCfg = crcConfig('Polynomial', polynomial, ...
            'InitialConditions', initialConditions, ...
            'DirectMethod', true);
        codeword = crcGenerate(dataBits, crcCfg);
    else
        % 兼容尚未提供 crcConfig/crcGenerate 的旧 MATLAB release。
        crcGen = comm.CRCGenerator(polynomial, ...
            'InitialConditions', initialConditions, ...
            'DirectMethod', true);
        codeword = crcGen(dataBits);
    end
    codeword = double(codeword(:));
    expectedLength = numel(dataBits) + 24;
    if numel(codeword) ~= expectedLength
        error('BLEStudio:gen_ble_data:InvalidCrcLength', ...
            'CRC generator returned %d bits; expected PDU+CRC length %d.', ...
            numel(codeword), expectedLength);
    end
end

function [waveform, interval] = apply_packet_interval(activeWaveform, sampleRate, packetDurationUs, enabled)
    activeWaveform = activeWaveform(:);
    activeSamples = numel(activeWaveform);
    if enabled
        intervalUs = ceil((packetDurationUs + 249) / 625) * 625;
        targetSamples = round(intervalUs * sampleRate / 1e6);
    else
        intervalUs = activeSamples / sampleRate * 1e6;
        targetSamples = activeSamples;
    end
    if targetSamples < activeSamples
        error('BLEStudio:gen_ble_data:InvalidIntervalSamples', ...
            'Packet interval target is smaller than active waveform.');
    end
    targetSamples = round(targetSamples);
    padSamples = targetSamples - activeSamples;
    waveform = [activeWaveform; complex(zeros(padSamples, 1))];
    interval = struct('enabled', logical(enabled), ...
        'active_samples', activeSamples, ...
        'padding_samples', padSamples, ...
        'target_samples', targetSamples, ...
        'interval_us', intervalUs, ...
        'actual_interval_us', targetSamples / sampleRate * 1e6);
end

function waveform = fit_sample_count(waveform, targetSamples)
    waveform = waveform(:);
    if numel(waveform) > targetSamples
        waveform = waveform(1:targetSamples);
    elseif numel(waveform) < targetSamples
        waveform = [waveform; complex(zeros(targetSamples - numel(waveform), 1))];
    end
end

function adcClockHz = calculate_adc_clock(rate, chanIdx)
    % 该公式来自原脚本的芯片 ADC 时钟假设；这里只提取常量，不改变硬件定义。
    pllBaseMHz = 2400;
    channelStepMHz = 2;
    referenceClockHz = 8e6;
    referenceDivider = 3;
    adcDivider = 132;
    if rate == 1
        offsetMHz = -2;
    else
        offsetMHz = -1;
    end
    pllWordMHz = pllBaseMHz + (chanIdx + 1) * channelStepMHz + offsetMHz;
    adcClockHz = pllWordMHz * referenceClockHz / referenceDivider / adcDivider;
end

function [noisyWaveform, noisePower] = add_awgn_active_power(waveform, activeSamples, snrDb, seed)
    waveform = waveform(:);
    if activeSamples < 1 || activeSamples > numel(waveform)
        error('BLEStudio:gen_ble_data:InvalidActiveSamples', ...
            'activeSamples must be within the waveform length.');
    end
    previousRng = rng;
    cleanupRng = onCleanup(@() rng(previousRng)); %#ok<NASGU>
    rng(seed, 'twister');
    activePower = mean(abs(waveform(1:activeSamples)).^2);
    noisePower = activePower / 10^(snrDb / 10);
    noise = sqrt(noisePower / 2) * ...
        (randn(size(waveform)) + 1i * randn(size(waveform)));
    noisyWaveform = waveform + noise;
end

function verify_ideal_rx(waveform, sampleRate, phyMode, sps, chanIdx, ...
        modulationIndex, pulseLength, expectedBits, expectedAccessAddress, ...
        noiseVariance, failOnError)
    args = {'Mode', phyMode, 'SamplesPerSymbol', round(sps), ...
        'ChannelIndex', chanIdx, 'WhitenStatus', 'Off', ...
        'ModulationIndex', modulationIndex, 'PulseLength', pulseLength};
    if noiseVariance > 0
        args = [args, {'NoiseVariance', noiseVariance}]; %#ok<AGROW>
    end
    try
        [rxBits, rxAccessAddress] = bleIdealReceiver(waveform(:), args{:});
        rxBits = double(rxBits(:));
        rxAccessAddress = double(rxAccessAddress(:));
        if ~isequal(rxAccessAddress, double(expectedAccessAddress(:)))
            error('Access address mismatch.');
        end
        if numel(rxBits) ~= numel(expectedBits)
            error('Bit length mismatch: expected %d, got %d.', numel(expectedBits), numel(rxBits));
        end
        [bitErrors, ber] = biterr(double(expectedBits(:)), rxBits);
        if bitErrors ~= 0
            error('RX bit errors=%d, BER=%g.', bitErrors, ber);
        end
        fprintf('Ideal RX check passed: %s, Fs=%.6g MHz\n', phyMode, sampleRate / 1e6);
    catch err
        if failOnError
            error('BLEStudio:gen_ble_data:IdealRxCheckFailed', ...
                'Ideal RX check failed: %s', err.message);
        end
        warning('BLEStudio:gen_ble_data:AwgnRxCheckFailed', ...
            'AWGN RX check failed: %s', err.message);
    end
end

function metadata = make_metadata(kind, phyMode, sourceFs, outputFs, sps, ...
        chanIdx, accessAddressValue, headerValue, payloadLenBytes, crcInitValue, ...
        packetDurationUs, interval, resampleEnabled, P, Q, adcClockHz, ...
        awgnEnabled, awgnSnrDb, noisePower, modulationIndex, pulseLength, ...
        awgnSeed, amplitudeScale, activeSignalPower, packetInfo)
    metadata = struct();
    metadata.schema_version = 1;
    metadata.output_kind = kind;
    metadata.phy_mode = phyMode;
    metadata.source_sample_rate_hz = sourceFs;
    metadata.sample_rate_hz = outputFs;
    metadata.samples_per_symbol = sps;
    metadata.symbol_rate_hz = outputFs / sps;
    metadata.channel_index = chanIdx;
    metadata.access_address = sprintf('0x%08X', accessAddressValue);
    metadata.header_value = headerValue;
    metadata.payload_type = dtm_payload_name(headerValue);
    metadata.payload_length_bytes = payloadLenBytes;
    metadata.payload_hex = packetInfo.payload_hex;
    metadata.crc_init = sprintf('0x%06X', crcInitValue);
    metadata.crc_polynomial = packetInfo.crc_polynomial;
    metadata.whitening = 'Off';
    metadata.modulation_index = modulationIndex;
    metadata.pulse_length = pulseLength;
    metadata.amplitude_scale = amplitudeScale;
    metadata.active_signal_power = activeSignalPower;
    metadata.packet_duration_us = packetDurationUs;
    metadata.active_samples = interval.active_samples;
    metadata.padding_samples = interval.padding_samples;
    metadata.target_samples = interval.target_samples;
    metadata.packet_interval_enabled = interval.enabled;
    metadata.packet_interval_us = interval.interval_us;
    metadata.actual_interval_us = interval.actual_interval_us;
    metadata.resample_enabled = logical(resampleEnabled);
    metadata.resample_p = P;
    metadata.resample_q = Q;
    metadata.adc_clock_hz = adcClockHz;
    metadata.awgn_enabled = logical(awgnEnabled);
    metadata.awgn_snr_db = awgnSnrDb;
    metadata.awgn_noise_power = noisePower;
    metadata.awgn_seed = awgnSeed;
    metadata.quantization_bit_width = 12;
    metadata.quantization_fraction_bits = 11;
    metadata.quantization_saturation = true;
    metadata.iq_pack = 'I high 12 bits, Q low 12 bits';
    metadata.rounding_policy = 'MATLAB round, ties away from zero, applied to real and imaginary I/Q components';
    metadata.txt_format = 'packed hexadecimal I[11:0] followed by Q[11:0]';
    metadata.sample_count = interval.target_samples;
    metadata.resample_raw_samples = 0;
    metadata.resample_adjustment_samples = 0;
    if awgnEnabled
        metadata.awgn_stage = 'native_rate';
    else
        metadata.awgn_stage = 'not applicable';
    end
    metadata.pdu_hex = packetInfo.pdu_hex;
    metadata.pdu_with_crc_hex = packetInfo.pdu_with_crc_hex;
end

function name = dtm_payload_name(headerValue)
    names = {'PRBS9', '11110000', '10101010', 'PRBS15', ...
        '11111111', '00000000', '00001111', '01010101'};
    name = names{headerValue + 1};
end

function outputInfo = save_waveform_bundle(outputDir, stem, waveform, sampleRateHz, ...
        metadata, packetInfo, writeTxt)
    waveform = waveform(:);
    LEWaveform = waveform; %#ok<NASGU>
    Fs = sampleRateHz; %#ok<NASGU>
    PDU = packetInfo.pdu; %#ok<NASGU>
    PDUCRC = packetInfo.pdu_crc; %#ok<NASGU>
    PayloadBits = packetInfo.payload_bits; %#ok<NASGU>
    AccessAddressBits = packetInfo.access_address_bits; %#ok<NASGU>

    matPath = fullfile(outputDir, [stem, '.mat']);
    save(matPath, 'LEWaveform', 'Fs', 'metadata', 'PDU', 'PDUCRC', ...
        'PayloadBits', 'AccessAddressBits', '-v7');

    txtPath = '';
    if writeTxt
        txtPath = fullfile(outputDir, [stem, '.txt']);
        write_iq_txt(waveform, txtPath, 12);
    end

    jsonPath = fullfile(outputDir, [stem, '.json']);
    hasJsonEncode = exist('jsonencode', 'file') == 2 || ...
        exist('jsonencode', 'builtin') == 5;
    if hasJsonEncode
        fid = fopen(jsonPath, 'w');
        if fid < 0
            error('BLEStudio:gen_ble_data:OpenMetadata', ...
                'Cannot open metadata file "%s".', jsonPath);
        end
        cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
        jsonText = jsonencode(metadata, 'PrettyPrint', true);
        fprintf(fid, '%s\n', jsonText);
    else
        jsonPath = '';
        warning('BLEStudio:gen_ble_data:NoJsonEncode', ...
            'jsonencode is unavailable; metadata remains in the MAT file.');
    end

    outputInfo = struct('mat', matPath, 'txt', txtPath, 'json', jsonPath, ...
        'samples', numel(waveform), 'sample_rate_hz', sampleRateHz);
    fprintf('[%s] %d samples at %.9g MHz\n', metadata.output_kind, ...
        numel(waveform), sampleRateHz / 1e6);
end

function write_iq_txt(waveform, filePath, bitWidth)
    I = real(waveform);
    Q = imag(waveform);
    intI = quantize_nm(I, 1, bitWidth - 1) * 2^(bitWidth - 1);
    intQ = quantize_nm(Q, 1, bitWidth - 1) * 2^(bitWidth - 1);
    hexI = mydec2comphex(intI, bitWidth);
    hexQ = mydec2comphex(intQ, bitWidth);
    if size(hexI, 1) ~= numel(waveform) || size(hexQ, 1) ~= numel(waveform)
        error('BLEStudio:gen_ble_data:QuantizedLength', ...
            'Quantized I/Q length does not match waveform length.');
    end
    fid = fopen(filePath, 'w');
    if fid < 0
        error('BLEStudio:gen_ble_data:OpenIqText', ...
            'Cannot open IQ text file "%s".', filePath);
    end
    cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
    for index = 1:numel(waveform)
        fprintf(fid, '%s%s\n', hexI(index, :), hexQ(index, :));
    end
end

function flag = validate_flag(value, name)
    validateattributes(value, {'numeric', 'logical'}, ...
        {'real', 'finite', 'scalar'}, mfilename, name);
    if value ~= 0 && value ~= 1
        error('BLEStudio:gen_ble_data:InvalidFlag', ...
            '%s must be 0 or 1.', name);
    end
    flag = logical(value);
end

function token = rate_token(sampleRateHz)
    token = number_token(sampleRateHz / 1e6);
end

function stem = make_native_stem(phyMode, sampleRateHz, chanIdx, ...
        headerValue, payloadLenBytes, intervalEnabled)
    % 默认 canonical vector 保留历史文件名；其他配置附带关键参数避免覆盖。
    isCanonical = chanIdx == 32 && headerValue == 0 && ...
        payloadLenBytes == 37 && ~intervalEnabled;
    if isCanonical
        stem = sprintf('%s_%sMsps', phyMode, rate_token(sampleRateHz));
        return;
    end
    if intervalEnabled
        intervalToken = 'interval';
    else
        intervalToken = 'packet';
    end
    stem = sprintf('%s_%sMsps_ch%d_t%d_len%d_%s', ...
        phyMode, rate_token(sampleRateHz), chanIdx, headerValue, ...
        payloadLenBytes, intervalToken);
end

function token = number_token(value)
    token = sprintf('%.9g', value);
    token = strrep(token, '-', 'm');
    token = strrep(token, '.', 'p');
end

function hexText = bits_lsb_to_hex(bits)
    bits = double(bits(:));
    if isempty(bits)
        hexText = '';
        return;
    end
    if mod(numel(bits), 8) ~= 0 || any(bits ~= 0 & bits ~= 1)
        error('BLEStudio:gen_ble_data:InvalidBits', ...
            'Bits must contain an integer number of binary octets.');
    end
    numBytes = numel(bits) / 8;
    byteValues = zeros(1, numBytes);
    for byteIndex = 1:numBytes
        byteBits = bits((byteIndex - 1) * 8 + (1:8));
        byteValues(byteIndex) = sum(byteBits(:)' .* 2.^(0:7));
    end
    hexText = lower(reshape(dec2hex(byteValues, 2).', 1, []));
end
