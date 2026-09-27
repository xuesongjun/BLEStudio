function hexStr = mydec2comphex(a, bitLen)
    %MYDEC2COMPHEX 将有符号整数转换为固定宽度的二进制补码十六进制字符串。
    %   每个输入元素对应一行，输出宽度固定为 ceil(bitLen / 4)。

    validateattributes(a, {'numeric'}, {'vector', 'nonempty'}, ...
        mfilename, 'a', 1);
    if any(isnan(a(:)) | isinf(a(:)))
        error('mydec2comphex:NonFinite', ...
            'Input must contain only finite values.');
    end
    if any(imag(a(:)) ~= 0)
        error('mydec2comphex:ComplexInput', ...
            'Input must be real-valued.');
    end
    a = real(a);
    validateattributes(a, {'numeric'}, {'finite', 'integer'}, ...
        mfilename, 'a', 1);
    validateattributes(bitLen, {'numeric'}, ...
        {'real', 'finite', 'scalar', 'integer', '>=', 1, '<=', 52}, ...
        mfilename, 'bitLen', 2);

    minValue = -2^(bitLen - 1);
    maxValue = 2^(bitLen - 1) - 1;
    if any(a(:) < minValue | a(:) > maxValue)
        error('mydec2comphex:OutOfRange', ...
            'Input must be in the signed %d-bit range [%g, %g].', ...
            bitLen, minValue, maxValue);
    end

    % 使用 double 可保证 bitLen <= 52 时所有整数补码值均可精确表示。
    encoded = double(a(:));
    negative = encoded < 0;
    encoded(negative) = encoded(negative) + 2^bitLen;

    hexWidth = ceil(bitLen / 4);
    hexStr = dec2hex(encoded, hexWidth);
end
