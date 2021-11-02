function clipImageToQuantiles(img, low_quantile, high_quantile) {
    low_quantile = parseFloat(low_quantile);
    high_quantile = parseFloat(high_quantile);

    const [low, high] = math.quantileSeq(img, [low_quantile, high_quantile]);
    img = img.map(row => {
        return row.map(x => {
            if (x <= low) {
                x = low;
            } else if (x >= high) {
                x = high;
            }
            return x;
        });
    });
    return img;
}

async function bytesToMatrix(blob, dim = [512, 512]) {
    let data = await new Response(blob).arrayBuffer();
    data = new Uint16Array(data);
    data = Array.from(data);
    data = math.matrix(data);
    data = data.reshape(dim);
    return data;
}

function scaleToUint8(X) {
    const max = math.max(X);
    const min = math.min(X);

    X = X.map(row => {
        return row.map(x => {
            return Math.floor((x - min) / (max - min) * 255);
        });
    });
    return X;
}

function toRGB(X) {
    X = X.map(row => {
        return row.map(x => {
            return [x, x, x];
        });
    });
    return X;
}

export {
    clipImageToQuantiles,
    bytesToMatrix,
    scaleToUint8,
    toRGB
}