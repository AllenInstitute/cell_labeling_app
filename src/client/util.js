function clipImageToQuantiles(img, low_quantile, high_quantile) {
    /* Clip image to quantiles 
        Args:
            - img: Array
                The img to clip
            - low_quantile: float
                low quantile to clip
            - high_quantile: float
                high quantile to clip

    */
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
    /* Converts a bytes representation of a matrix to a matrix 
        Args:
            -blob: Blob
            - dim: Array
                dimension of the matrix
    */
    let data = await new Response(blob).arrayBuffer();
    data = new Uint16Array(data);
    data = Array.from(data);
    data = math.matrix(data);
    data = data.reshape(dim);
    return data;
}

function scaleToUint8(X) {
    /* Scales an input to Uint8 
        Args:
            - X: Array
                The array to scale
    */
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
    /* Converts a grayscale input to 3 channels
        Args:
            - X: Array
    */
    X = X.map(row => {
        return row.map(x => {
            return [x, x, x];
        });
    });
    return X;
}

function displayTemporaryAlert({msg, type, showTime = 5000} = {}) {
    /* Displays an alert at top of page that hides after showTime ms
    
    Args
    --------
    - msg:
        The message to display
    - type:
        The type of alert (success, danger, etc. Bootstrap classes)
    - showTime:
        The amount of time to display the alert in ms
    */

    let alert = `
        <div class="alert alert-${type} fade show" role="alert" style="margin-top: 20px" id="alert">
            ${msg}
        </div>`;
    alert = $(alert);
    $('#alert-container').html(alert);
    setTimeout(() => $('#alert').alert('close'), showTime);
}

export {
    clipImageToQuantiles,
    bytesToMatrix,
    scaleToUint8,
    toRGB,
    displayTemporaryAlert
}