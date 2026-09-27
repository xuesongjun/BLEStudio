function y = quantize_nm(x, n, m)
    %QUANTIZE_NM 将输入量化为包含 n 位整数和 m 位小数的定点数。
    %   n 包含符号位，因此 n 必须至少为 1；m 必须为非负整数。
    %   实部和虚部均使用 MATLAB round，保证 I/Q 量化规则一致。

    validateattributes(x, {'numeric'}, {'nonempty', 'finite'}, ...
        mfilename, 'x', 1);
    validateattributes(n, {'numeric'}, ...
        {'real', 'finite', 'scalar', 'integer', '>=', 1}, ...
        mfilename, 'n', 2);
    validateattributes(m, {'numeric'}, ...
        {'real', 'finite', 'scalar', 'integer', '>=', 0}, ...
        mfilename, 'm', 3);

    minValue = -2^(n - 1);
    maxValue = 2^(n - 1) - 2^(-m);
    scale = 2^m;

    %% 实部：饱和后按最近整数取整
    xReal = real(x);
    realOverflow = xReal > maxValue | xReal < minValue;
    if any(realOverflow(:))
        warning('quantize_nm:Overflow', ...
            'Real input exceeds the representable range and was saturated.');
        xReal = min(max(xReal, minValue), maxValue);
    end
    yReal = round(xReal * scale) / scale;

    %% 虚部：使用与实部相同的最近值取整规则
    xImag = imag(x);
    imagOverflow = xImag > maxValue | xImag < minValue;
    if any(imagOverflow(:))
        warning('quantize_nm:Overflow', ...
            'Imaginary input exceeds the representable range and was saturated.');
        xImag = min(max(xImag, minValue), maxValue);
    end
    yImag = round(xImag * scale) / scale;

    y = yReal + 1i * yImag;
end
