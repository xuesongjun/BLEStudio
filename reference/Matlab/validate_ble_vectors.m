function report = validate_ble_vectors(referenceDir)
%VALIDATE_BLE_VECTORS 校验 BLE Core DTM golden vector 和 clean IQ reference。
%   REPORT = VALIDATE_BLE_VECTORS() 校验 reference/BLE_PKT 下的 8 Msps 和
%   96 Msps LE 1M clean reference。校验失败时抛出带定位信息的错误。
%
%   REPORT = VALIDATE_BLE_VECTORS(REFERENCEDIR) 可指定 reference 文件目录。
%
%   本文件不调用 comm.PNSequence 或 bleWaveformGenerator 生成期望数据，
%   避免被测实现与验证实现采用同一错误 convention 后仍然通过。

    if nargin < 1 || isempty(referenceDir)
        matlabDir = fileparts(mfilename('fullpath'));
        referenceDir = fullfile(fileparts(matlabDir), 'BLE_PKT');
    end

    if exist(referenceDir, 'dir') ~= 7
        error('BLEStudio:GoldenVector:MissingDirectory', ...
            'Reference directory does not exist: %s', referenceDir);
    end

    payloadLengthBytes = 37;
    headerValue = 0;
    channelIndex = 32;
    accessAddress = uint32(hex2dec('71764129'));
    crcInit = uint32(hex2dec('555555'));

    %% 1. BLE Core DTM PRBS9 golden payload
    % 完整 37-byte payload 是 transmission order 下按 byte 打包的固定答案；
    % 每个 byte 内第一个发送的 bit 放在 bit 0。
    expectedPayloadHex = [ ...
        'ffc1fbe84c90728be7b3518963ab232302841872aa612f3b51a8e53749fb' ...
        'c9ca0c18532cfd'];
    expectedPayloadBytes = hex_to_bytes(expectedPayloadHex);
    expectedPayloadBits = bytes_to_bits_lsb(expectedPayloadBytes);

    generatedPayloadBits = generate_core_prbs9(payloadLengthBytes * 8);
    generatedPayloadBytes = bits_to_bytes_lsb(generatedPayloadBits);
    require_equal(generatedPayloadBytes, expectedPayloadBytes, ...
        'BLE Core PRBS9 full 37-byte payload');

    expectedPrefix = '11111111100000111101';
    actualPrefix = bits_to_text(generatedPayloadBits(1:numel(expectedPrefix)));
    require_true(strcmp(actualPrefix, expectedPrefix), ...
        'BLE Core PRBS9 prefix mismatch.');

    %% 1.1 BLE Core DTM PRBS15 golden payload
    expectedPrbs15Hex = [ ...
        'ff7f00200018000a800720029801aa807f202018180a8a8727229a99ab2aff5' ...
        'f0038001280'];
    expectedPrbs15Bytes = hex_to_bytes(expectedPrbs15Hex);
    generatedPrbs15Bits = generate_core_prbs15(payloadLengthBytes * 8);
    generatedPrbs15Bytes = bits_to_bytes_lsb(generatedPrbs15Bits);
    require_equal(generatedPrbs15Bytes, expectedPrbs15Bytes, ...
        'BLE Core PRBS15 full 37-byte payload');
    require_true(strcmp(bits_to_text(generatedPrbs15Bits(1:20)), ...
        '11111111111111100000'), 'BLE Core PRBS15 prefix mismatch.');

    %% 2. DTM PDU、Access Address、CRC 和 whitening-off bitstream
    headerBytes = uint8([headerValue, payloadLengthBytes]);
    headerBits = bytes_to_bits_lsb(headerBytes);
    require_true(strcmp(bits_to_text(headerBits), '0000000010100100'), ...
        'DTM header or payload length bit order mismatch.');

    expectedPduBits = [headerBits; expectedPayloadBits];
    expectedCrcBits = calculate_ble_crc_bits(expectedPduBits, crcInit);
    require_true(strcmp(bits_to_text(expectedCrcBits), ...
        '111000100010000111101000'), ...
        'DTM CRC golden vector mismatch.');

    expectedPduCrcBits = [expectedPduBits; expectedCrcBits];
    expectedAccessAddressBits = integer_to_bits_lsb(accessAddress, 32);
    require_true(strcmp(bits_to_text(expectedAccessAddressBits), ...
        '10010100100000100110111010001110'), ...
        'Access Address transmission-order vector mismatch.');

    % 0x71764129 的 LSB 为 1，因此 LE 1M preamble 从 1 开始交替。
    expectedPreambleBits = uint8([1; 0; 1; 0; 1; 0; 1; 0]);
    expectedPacketBits = [ ...
        expectedPreambleBits; expectedAccessAddressBits; expectedPduCrcBits];
    require_true(numel(expectedPacketBits) == 376, ...
        'Unexpected LE 1M packet bit count.');

    %% 2.1 通用 fixed-point helper golden vectors
    fixedPointReport = validate_fixed_point_helpers();

    %% 3. 8/96 Msps clean reference 和 metadata
    sampleRates = [8e6, 96e6];
    stems = {'LE1M_8Msps', 'LE1M_96Msps'};
    vectorReports = repmat(struct( ...
        'stem', '', ...
        'sampleRate', 0, ...
        'sampleCount', 0, ...
        'txtFormat', '', ...
        'jsonChecked', false), 1, numel(sampleRates));

    for vectorIndex = 1:numel(sampleRates)
        vectorReports(vectorIndex) = validate_clean_vector( ...
            referenceDir, stems{vectorIndex}, sampleRates(vectorIndex), ...
            channelIndex, accessAddress, crcInit, expectedPacketBits, ...
            expectedPayloadBits, expectedPduBits, expectedPduCrcBits, ...
            expectedAccessAddressBits);
    end

    report = struct();
    report.passed = true;
    report.referenceDir = referenceDir;
    report.prbs9PayloadHex = upper(expectedPayloadHex);
    report.prbs15PayloadHex = upper(expectedPrbs15Hex);
    report.crc = '0x178447';
    report.packetBitCount = numel(expectedPacketBits);
    report.fixedPoint = fixedPointReport;
    report.vectors = vectorReports;

    fprintf('BLE Core DTM golden vectors passed.\n');
    fprintf('  Fixed-point helpers: 12-bit hex and half-LSB checks passed.\n');
    for vectorIndex = 1:numel(vectorReports)
        fprintf('  %s: %d samples, MAT/TXT match (%s).\n', ...
            vectorReports(vectorIndex).stem, ...
            vectorReports(vectorIndex).sampleCount, ...
            vectorReports(vectorIndex).txtFormat);
    end
end


function helperReport = validate_fixed_point_helpers()
%VALIDATE_FIXED_POINT_HELPERS 校验通用定点 helper 的边界和 rounding 契约。

    inputIntegers = [-2048; -1; 0; 1; 2047];
    expectedHex = ['800'; 'FFF'; '000'; '001'; '7FF'];
    actualHex = mydec2comphex(inputIntegers, 12);
    require_equal(actualHex, expectedHex, ...
        'mydec2comphex 12-bit two''s-complement boundaries');

    halfLsb = 2^-12;
    quantized = real(quantize_nm([-halfLsb; halfLsb], 1, 11));
    expectedQuantized = [-2^-11; 2^-11];
    require_equal(quantized, expectedQuantized, ...
        'quantize_nm real half-LSB rounding');

    complexQuantized = quantize_nm(1i * [halfLsb; -halfLsb], 1, 11);
    require_equal(imag(complexQuantized), [2^-11; -2^-11], ...
        'quantize_nm imaginary half-LSB rounding');

    helperReport = struct();
    helperReport.bitWidth = 12;
    helperReport.hexBoundaries = cellstr(actualHex);
    helperReport.halfLsb = halfLsb;
end


function vectorReport = validate_clean_vector(referenceDir, stem, sampleRate, ...
        channelIndex, accessAddress, crcInit, expectedPacketBits, ...
        expectedPayloadBits, expectedPduBits, expectedPduCrcBits, ...
        expectedAccessAddressBits)
%VALIDATE_CLEAN_VECTOR 校验一组 clean MAT/TXT/JSON reference。

    matPath = fullfile(referenceDir, [stem, '.mat']);
    txtPath = fullfile(referenceDir, [stem, '.txt']);
    jsonPath = fullfile(referenceDir, [stem, '.json']);

    require_file(matPath);
    require_file(txtPath);

    saved = load(matPath);
    requiredFields = { ...
        'LEWaveform', 'Fs', 'metadata', 'PDU', 'PDUCRC', ...
        'PayloadBits', 'AccessAddressBits'};
    for fieldIndex = 1:numel(requiredFields)
        fieldName = requiredFields{fieldIndex};
        require_true(isfield(saved, fieldName), sprintf( ...
            'MAT file %s is missing required field %s.', matPath, fieldName));
    end

    waveform = saved.LEWaveform(:);
    require_true(isnumeric(waveform) && ~isempty(waveform), ...
        sprintf('LEWaveform in %s must be a non-empty numeric vector.', matPath));
    waveformFinite = ~isnan(real(waveform)) & ~isinf(real(waveform)) & ...
        ~isnan(imag(waveform)) & ~isinf(imag(waveform));
    require_true(all(waveformFinite), ...
        sprintf('LEWaveform in %s contains non-finite samples.', matPath));

    fsValue = scalar_number(saved.Fs, 'Fs');
    require_close(fsValue, sampleRate, 0.5, ...
        sprintf('Fs in %s', matPath));

    samplesPerSymbol = sampleRate / 1e6;
    require_true(samplesPerSymbol == round(samplesPerSymbol), ...
        sprintf('Sample rate %.17g is not an integer SPS for LE 1M.', sampleRate));
    expectedSampleCount = numel(expectedPacketBits) * samplesPerSymbol;
    require_true(numel(waveform) == expectedSampleCount, sprintf( ...
        '%s has %d samples; expected %d.', ...
        matPath, numel(waveform), expectedSampleCount));

    payloadBits = normalize_saved_bits( ...
        saved.PayloadBits, numel(expectedPayloadBits), 'PayloadBits');
    pduBits = normalize_saved_bits( ...
        saved.PDU, numel(expectedPduBits), 'PDU');
    pduCrcBits = normalize_saved_bits( ...
        saved.PDUCRC, numel(expectedPduCrcBits), 'PDUCRC');
    accessAddressBits = normalize_saved_bits( ...
        saved.AccessAddressBits, numel(expectedAccessAddressBits), ...
        'AccessAddressBits');

    require_equal(payloadBits, expectedPayloadBits, ...
        sprintf('%s PayloadBits', stem));
    require_equal(pduBits, expectedPduBits, sprintf('%s PDU', stem));
    % WhitenStatus=Off 时，送入调制器的数据必须就是未白化的 PDU+CRC。
    require_equal(pduCrcBits, expectedPduCrcBits, ...
        sprintf('%s whitening-off PDUCRC', stem));
    require_equal(accessAddressBits, expectedAccessAddressBits, ...
        sprintf('%s AccessAddressBits', stem));

    bitWidth = validate_metadata(saved.metadata, sampleRate, ...
        samplesPerSymbol, expectedSampleCount, channelIndex, ...
        accessAddress, crcInit, stem);

    [txtI, txtQ, txtFormat] = read_iq_txt( ...
        txtPath, bitWidth, expectedSampleCount);
    [expectedI, expectedQ] = quantize_waveform(waveform, bitWidth);
    require_equal(txtI, expectedI, sprintf('%s TXT I samples', stem));
    require_equal(txtQ, expectedQ, sprintf('%s TXT Q samples', stem));

    if exist(jsonPath, 'file') == 2
        jsonChecked = validate_json_file(jsonPath, sampleRate, expectedSampleCount);
    else
        jsonChecked = false;
    end

    vectorReport = struct();
    vectorReport.stem = stem;
    vectorReport.sampleRate = sampleRate;
    vectorReport.sampleCount = numel(waveform);
    vectorReport.txtFormat = txtFormat;
    vectorReport.jsonChecked = jsonChecked;
end


function bitWidth = validate_metadata(metadata, sampleRate, ...
        samplesPerSymbol, sampleCount, channelIndex, accessAddress, ...
        crcInit, stem)
%VALIDATE_METADATA 检查复现 clean reference 所需的关键配置。

    require_true(isstruct(metadata) && isscalar(metadata), ...
        sprintf('%s metadata must be a scalar struct.', stem));

    phyMode = metadata_value(metadata, ...
        {'phy_mode', 'phyMode', 'phy', 'mode'}, 'PHY mode');
    require_true(strcmpi(text_value(phyMode, 'PHY mode'), 'LE1M'), ...
        sprintf('%s metadata PHY mode must be LE1M.', stem));

    actualRate = scalar_number(metadata_value(metadata, ...
        {'sample_rate_hz', 'sampleRate', 'sampleRateHz', 'Fs', 'FsOut'}, ...
        'sample rate'), 'sample rate');
    require_close(actualRate, sampleRate, 0.5, ...
        sprintf('%s metadata sample rate', stem));

    actualSps = scalar_number(metadata_value(metadata, ...
        {'samples_per_symbol', 'samplesPerSymbol', 'sps'}, ...
        'samples per symbol'), ...
        'samples per symbol');
    require_close(actualSps, samplesPerSymbol, 0, ...
        sprintf('%s metadata samples per symbol', stem));

    actualCount = scalar_number(metadata_value(metadata, ...
        {'target_samples', 'sampleCount', 'numSamples'}, ...
        'sample count'), 'sample count');
    require_close(actualCount, sampleCount, 0, ...
        sprintf('%s metadata sample count', stem));

    actualChannel = scalar_number(metadata_value(metadata, ...
        {'channel_index', 'channelIndex', 'chanIdx', 'channel'}, ...
        'channel index'), ...
        'channel index');
    require_close(actualChannel, channelIndex, 0, ...
        sprintf('%s metadata channel index', stem));

    actualAccessAddress = integer_value(metadata_value(metadata, ...
        {'access_address', 'accessAddress', 'syncword'}, ...
        'Access Address'), 'Access Address');
    require_close(actualAccessAddress, double(accessAddress), 0, ...
        sprintf('%s metadata Access Address', stem));

    actualCrcInit = integer_value(metadata_value(metadata, ...
        {'crc_init', 'crcInit', 'CRCInit'}, 'CRC init'), 'CRC init');
    require_close(actualCrcInit, double(crcInit), 0, ...
        sprintf('%s metadata CRC init', stem));

    whitening = metadata_value(metadata, ...
        {'whitening', 'whitenStatus', 'whiteningEnabled'}, ...
        'whitening status');
    require_true(is_whitening_off(whitening), ...
        sprintf('%s metadata must state whitening is Off.', stem));

    outputKind = metadata_value(metadata, ...
        {'output_kind', 'outputKind', 'waveformKind', 'kind', 'outputType'}, ...
        'output kind');
    require_true(strcmpi(text_value(outputKind, 'output kind'), 'clean_tx'), ...
        sprintf('%s metadata output kind must be clean_tx.', stem));

    headerValue = scalar_number(metadata_value(metadata, ...
        {'header_value', 'headerValue'}, 'DTM header value'), ...
        'DTM header value');
    require_close(headerValue, 0, 0, ...
        sprintf('%s metadata DTM header value', stem));

    payloadLength = scalar_number(metadata_value(metadata, ...
        {'payload_length_bytes', 'payloadLengthBytes'}, 'payload length'), ...
        'payload length');
    require_close(payloadLength, 37, 0, ...
        sprintf('%s metadata payload length', stem));

    payloadType = metadata_value(metadata, ...
        {'payload_type', 'payloadType'}, 'payload type');
    require_true(strcmpi(text_value(payloadType, 'payload type'), 'PRBS9'), ...
        sprintf('%s metadata payload type must be PRBS9.', stem));

    amplitudeScale = scalar_number(metadata_value(metadata, ...
        {'amplitude_scale', 'amplitudeScale'}, 'amplitude scale'), ...
        'amplitude scale');
    require_close(amplitudeScale, 1, 0, ...
        sprintf('%s metadata amplitude scale', stem));

    activeSignalPower = scalar_number(metadata_value(metadata, ...
        {'active_signal_power', 'activeSignalPower'}, 'active signal power'), ...
        'active signal power');
    require_close(activeSignalPower, 1, 1e-12, ...
        sprintf('%s metadata active signal power', stem));

    resampleEnabled = metadata_value(metadata, ...
        {'resample_enabled', 'resampleEnabled'}, 'resample status');
    require_false_flag(resampleEnabled, ...
        sprintf('%s metadata resample_enabled', stem));

    awgnEnabled = metadata_value(metadata, ...
        {'awgn_enabled', 'awgnEnabled'}, 'AWGN status');
    require_false_flag(awgnEnabled, ...
        sprintf('%s metadata awgn_enabled', stem));

    intervalEnabled = metadata_value(metadata, ...
        {'packet_interval_enabled', 'packetIntervalEnabled'}, ...
        'packet interval status');
    require_false_flag(intervalEnabled, ...
        sprintf('%s metadata packet_interval_enabled', stem));

    paddingSamples = scalar_number(metadata_value(metadata, ...
        {'padding_samples', 'paddingSamples'}, 'padding sample count'), ...
        'padding sample count');
    require_close(paddingSamples, 0, 0, ...
        sprintf('%s metadata padding sample count', stem));

    bitWidth = metadata_bit_width(metadata);
    require_true(bitWidth == 12, ...
        sprintf('%s metadata bit width must be 12.', stem));

    fractionBits = scalar_number(metadata_value(metadata, ...
        {'quantization_fraction_bits', 'fractionBits'}, ...
        'quantization fraction bits'), 'quantization fraction bits');
    require_close(fractionBits, 11, 0, ...
        sprintf('%s metadata quantization fraction bits', stem));
end


function bitWidth = metadata_bit_width(metadata)
%METADATA_BIT_WIDTH 同时兼容 flat 和 quantization 子结构。

    [hasQuantization, quantization] = optional_metadata_value( ...
        metadata, {'quantization'});
    if hasQuantization
        require_true(isstruct(quantization) && isscalar(quantization), ...
            'metadata.quantization must be a scalar struct.');
        value = metadata_value(quantization, ...
            {'bit_width', 'bitWidth', 'bits', 'wordLength'}, ...
            'quantization bit width');
    else
        value = metadata_value(metadata, ...
            {'quantization_bit_width', 'bitWidth', ...
            'quantizationBitWidth', 'iqWordWidthBits', 'wordLength'}, ...
            'quantization bit width');
    end
    bitWidth = scalar_number(value, 'quantization bit width');
end


function checked = validate_json_file(jsonPath, sampleRate, sampleCount)
%VALIDATE_JSON_FILE 旧 MATLAB 无 jsondecode 时仍检查 JSON 文件非空。

    jsonText = fileread(jsonPath);
    trimmedJsonText = strtrim(jsonText);
    require_true(~isempty(trimmedJsonText), ...
        sprintf('JSON metadata file is empty: %s', jsonPath));
    hasInternalLineBreak = ~isempty(regexp( ...
        trimmedJsonText, '\r\n|\r|\n', 'once'));
    require_true(hasInternalLineBreak, sprintf( ...
        'JSON metadata must be pretty-printed across multiple lines: %s', ...
        jsonPath));
    checked = false;

    hasJsonDecode = exist('jsondecode', 'builtin') == 5 || ...
        exist('jsondecode', 'file') == 2;
    if ~hasJsonDecode
        return;
    end

    decoded = jsondecode(jsonText);
    require_true(isstruct(decoded), ...
        sprintf('JSON metadata root must be an object: %s', jsonPath));
    if isfield(decoded, 'metadata') && isstruct(decoded.metadata)
        decoded = decoded.metadata;
    end

    [hasRate, rateValue] = optional_metadata_value(decoded, ...
        {'sample_rate_hz', 'sampleRate', 'sampleRateHz', 'Fs', 'FsOut'});
    if hasRate
        require_close(scalar_number(rateValue, 'JSON sample rate'), ...
            sampleRate, 0.5, sprintf('%s JSON sample rate', jsonPath));
    end

    [hasCount, countValue] = optional_metadata_value(decoded, ...
        {'target_samples', 'sampleCount', 'numSamples'});
    if hasCount
        require_close(scalar_number(countValue, 'JSON sample count'), ...
            sampleCount, 0, sprintf('%s JSON sample count', jsonPath));
    end
    checked = true;
end


function bits = generate_core_prbs9(bitCount)
%GENERATE_CORE_PRBS9 按 BLE transmission order 实现 x^9+x^5+1。
%   state bit 0 是当前输出，feedback=state[0] XOR state[4]，随后右移。

    state = uint16(hex2dec('1FF'));
    bits = zeros(bitCount, 1, 'uint8');
    for bitIndex = 1:bitCount
        bits(bitIndex) = uint8(bitand(state, uint16(1)));
        feedback = bitxor(bitget(state, 1), bitget(state, 5));
        state = bitor(bitshift(state, -1), ...
            bitshift(uint16(feedback), 8));
        state = bitand(state, uint16(hex2dec('1FF')));
    end
end


function bits = generate_core_prbs15(bitCount)
%GENERATE_CORE_PRBS15 按 BLE transmission order 实现 x^15+x^14+1。

    state = uint16(hex2dec('7FFF'));
    bits = zeros(bitCount, 1, 'uint8');
    for bitIndex = 1:bitCount
        bits(bitIndex) = uint8(bitand(state, uint16(1)));
        feedback = bitxor(bitget(state, 1), bitget(state, 2));
        state = bitor(bitshift(state, -1), ...
            bitshift(uint16(feedback), 14));
        state = bitand(state, uint16(hex2dec('7FFF')));
    end
end


function crcBits = calculate_ble_crc_bits(pduBits, crcInit)
%CALCULATE_BLE_CRC_BITS 计算与 BLE DTM direct-method 相同的 24-bit CRC。

    polynomial = uint32(hex2dec('00065B'));
    mask = uint32(hex2dec('FFFFFF'));
    crc = uint32(crcInit);
    pduBits = uint8(pduBits(:));

    for bitIndex = 1:numel(pduBits)
        msb = bitget(crc, 24);
        crc = bitand(bitshift(crc, 1), mask);
        if logical(bitxor(msb, uint32(pduBits(bitIndex))))
            crc = bitxor(crc, polynomial);
        end
    end

    % comm.CRCGenerator direct-method 输出对应寄存器值的 24-bit reverse。
    reversed = uint32(0);
    for bitIndex = 1:24
        if bitget(crc, bitIndex)
            reversed = bitset(reversed, 25 - bitIndex);
        end
    end
    crcBits = integer_to_bits_lsb(reversed, 24);
end


function bits = normalize_saved_bits(value, expectedBitCount, fieldName)
%NORMALIZE_SAVED_BITS 接受 bit vector；为兼容旧数据，也接受 LSB-first bytes。

    require_true(isnumeric(value) || islogical(value), ...
        sprintf('%s must be numeric or logical.', fieldName));
    values = double(value(:));

    if numel(values) == expectedBitCount && ...
            all(values == 0 | values == 1)
        bits = uint8(values);
        return;
    end

    if numel(values) * 8 == expectedBitCount && ...
            all(values >= 0 & values <= 255 & values == round(values))
        bits = bytes_to_bits_lsb(uint8(values));
        return;
    end

    error('BLEStudio:GoldenVector:InvalidBits', ...
        '%s must contain %d bits or %d LSB-first bytes.', ...
        fieldName, expectedBitCount, expectedBitCount / 8);
end


function [iValues, qValues, formatName] = read_iq_txt( ...
        txtPath, bitWidth, expectedSampleCount)
%READ_IQ_TXT 读取 packed hex 或两列 signed integer IQ 文件。

    fid = fopen(txtPath, 'rt');
    if fid < 0
        error('BLEStudio:GoldenVector:OpenFailed', ...
            'Cannot open IQ TXT file: %s', txtPath);
    end
    cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>

    iValues = zeros(expectedSampleCount, 1);
    qValues = zeros(expectedSampleCount, 1);
    sampleIndex = 0;
    detectedFormat = '';
    hexWidth = ceil(bitWidth / 4);

    while true
        line = fgetl(fid);
        if ~ischar(line)
            break;
        end
        line = strtrim(line);
        if isempty(line) || strncmp(line, '//', 2) || line(1) == '#'
            continue;
        end

        sampleIndex = sampleIndex + 1;
        require_true(sampleIndex <= expectedSampleCount, sprintf( ...
            '%s contains more than %d IQ samples.', ...
            txtPath, expectedSampleCount));

        packedPattern = ['^[0-9A-Fa-f]{', num2str(2 * hexWidth), '}$'];
        if ~isempty(regexp(line, packedPattern, 'once'))
            currentFormat = 'packed hex';
            iRaw = hex2dec(line(1:hexWidth));
            qRaw = hex2dec(line(hexWidth + 1:end));
            iValues(sampleIndex) = from_twos_complement(iRaw, bitWidth);
            qValues(sampleIndex) = from_twos_complement(qRaw, bitWidth);
        else
            values = sscanf(strrep(line, ',', ' '), '%f');
            valuesFinite = ~isnan(values) & ~isinf(values);
            require_true(numel(values) == 2 && all(valuesFinite) && ...
                all(values == round(values)), sprintf( ...
                'Invalid IQ line %d in %s: %s', ...
                sampleIndex, txtPath, line));
            currentFormat = 'two-column signed integer';
            iValues(sampleIndex) = values(1);
            qValues(sampleIndex) = values(2);
        end

        if isempty(detectedFormat)
            detectedFormat = currentFormat;
        else
            require_true(strcmp(detectedFormat, currentFormat), ...
                sprintf('Mixed IQ formats are not allowed in %s.', txtPath));
        end
    end

    require_true(sampleIndex == expectedSampleCount, sprintf( ...
        '%s contains %d IQ samples; expected %d.', ...
        txtPath, sampleIndex, expectedSampleCount));
    iValues = iValues(1:sampleIndex);
    qValues = qValues(1:sampleIndex);
    formatName = detectedFormat;
end


function [iValues, qValues] = quantize_waveform(waveform, bitWidth)
%QUANTIZE_WAVEFORM 复现 gen_ble_data 对分离 I/Q 的 round + saturation。

    scale = 2^(bitWidth - 1);
    minValue = -scale;
    maxValue = scale - 1;
    iValues = min(max(round(real(waveform) * scale), minValue), maxValue);
    qValues = min(max(round(imag(waveform) * scale), minValue), maxValue);
end


function signedValue = from_twos_complement(rawValue, bitWidth)
    signedValue = double(rawValue);
    if signedValue >= 2^(bitWidth - 1)
        signedValue = signedValue - 2^bitWidth;
    end
end


function bytes = hex_to_bytes(hexText)
    require_true(mod(numel(hexText), 2) == 0, ...
        'Hex golden vector must contain complete bytes.');
    bytes = zeros(numel(hexText) / 2, 1, 'uint8');
    for byteIndex = 1:numel(bytes)
        startIndex = (byteIndex - 1) * 2 + 1;
        bytes(byteIndex) = uint8(hex2dec( ...
            hexText(startIndex:startIndex + 1)));
    end
end


function bits = bytes_to_bits_lsb(bytes)
    bytes = uint8(bytes(:));
    bits = zeros(numel(bytes) * 8, 1, 'uint8');
    outputIndex = 1;
    for byteIndex = 1:numel(bytes)
        for bitIndex = 1:8
            bits(outputIndex) = uint8(bitget(bytes(byteIndex), bitIndex));
            outputIndex = outputIndex + 1;
        end
    end
end


function bytes = bits_to_bytes_lsb(bits)
    bits = uint8(bits(:));
    require_true(mod(numel(bits), 8) == 0, ...
        'Bit vector length must be a multiple of eight.');
    bytes = zeros(numel(bits) / 8, 1, 'uint8');
    for byteIndex = 1:numel(bytes)
        value = uint8(0);
        startIndex = (byteIndex - 1) * 8;
        for bitIndex = 1:8
            if bits(startIndex + bitIndex)
                value = bitset(value, bitIndex);
            end
        end
        bytes(byteIndex) = value;
    end
end


function bits = integer_to_bits_lsb(value, bitCount)
    bits = zeros(bitCount, 1, 'uint8');
    for bitIndex = 1:bitCount
        bits(bitIndex) = uint8(bitget(value, bitIndex));
    end
end


function text = bits_to_text(bits)
    text = char(double(bits(:).') + double('0'));
end


function value = metadata_value(metadata, aliases, label)
    [found, value] = optional_metadata_value(metadata, aliases);
    if ~found
        error('BLEStudio:GoldenVector:MissingMetadata', ...
            'Missing required metadata field for %s. Accepted names: %s', ...
            label, join_aliases(aliases));
    end
end


function [found, value] = optional_metadata_value(metadata, aliases)
    fields = fieldnames(metadata);
    found = false;
    value = [];
    for aliasIndex = 1:numel(aliases)
        matched = find(strcmpi(fields, aliases{aliasIndex}), 1);
        if ~isempty(matched)
            found = true;
            value = metadata.(fields{matched});
            return;
        end
    end
end


function text = join_aliases(aliases)
    text = aliases{1};
    for aliasIndex = 2:numel(aliases)
        text = [text, ', ', aliases{aliasIndex}]; %#ok<AGROW>
    end
end


function value = scalar_number(rawValue, label)
    require_true(isnumeric(rawValue) && isreal(rawValue) && ...
        isscalar(rawValue) && ~isnan(rawValue) && ~isinf(rawValue), ...
        sprintf('%s must be a finite real scalar.', label));
    value = double(rawValue);
end


function value = integer_value(rawValue, label)
    if isnumeric(rawValue)
        value = scalar_number(rawValue, label);
    else
        text = strtrim(text_value(rawValue, label));
        if numel(text) > 2 && strcmpi(text(1:2), '0x')
            value = hex2dec(text(3:end));
        else
            value = str2double(text);
        end
    end
    require_true(~isnan(value) && ~isinf(value) && value == round(value), ...
        sprintf('%s must be an integer.', label));
end


function text = text_value(rawValue, label)
    if ischar(rawValue)
        text = rawValue;
    elseif isa(rawValue, 'string') && isscalar(rawValue)
        text = char(rawValue);
    elseif iscell(rawValue) && isscalar(rawValue) && ischar(rawValue{1})
        text = rawValue{1};
    else
        error('BLEStudio:GoldenVector:InvalidMetadata', ...
            '%s must be text.', label);
    end
    text = strtrim(text);
end


function result = is_whitening_off(value)
    if islogical(value) || isnumeric(value)
        result = isscalar(value) && double(value) == 0;
        return;
    end
    text = lower(text_value(value, 'whitening status'));
    result = any(strcmp(text, {'off', 'false', 'disabled', '0'}));
end


function require_false_flag(value, label)
    validType = islogical(value) || isnumeric(value);
    require_true(validType && isscalar(value) && ...
        ~isnan(double(value)) && ~isinf(double(value)) && double(value) == 0, ...
        sprintf('%s must be false/0.', label));
end


function require_file(path)
    require_true(exist(path, 'file') == 2, ...
        sprintf('Required reference file does not exist: %s', path));
end


function require_close(actual, expected, tolerance, label)
    require_true(abs(actual - expected) <= tolerance, sprintf( ...
        '%s mismatch: actual %.17g, expected %.17g.', ...
        label, actual, expected));
end


function require_equal(actual, expected, label)
    if isequal(actual, expected)
        return;
    end

    actualVector = actual(:);
    expectedVector = expected(:);
    if numel(actualVector) == numel(expectedVector)
        firstMismatch = find(actualVector ~= expectedVector, 1);
        if ~isempty(firstMismatch)
            error('BLEStudio:GoldenVector:Mismatch', ...
                '%s mismatch at element %d: actual %g, expected %g.', ...
                label, firstMismatch, double(actualVector(firstMismatch)), ...
                double(expectedVector(firstMismatch)));
        end
    end

    error('BLEStudio:GoldenVector:Mismatch', ...
        '%s mismatch: actual size %s, expected size %s.', ...
        label, mat2str(size(actual)), mat2str(size(expected)));
end


function require_true(condition, message)
    if ~condition
        error('BLEStudio:GoldenVector:ValidationFailed', '%s', message);
    end
end
