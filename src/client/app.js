import img_data from "./img_data.js";

const display_projection = function() {
    const z = JSON.parse(img_data);
    const trace1 = {
        z: z,
        type: 'image'
    };

    const layout = {
        width: 512,
        height: 512,
        margin: {
            t: 30,
            l: 30,
            r: 30,
            b: 30
        },
        xaxis: {
            range: [200, 300]
        },
        yaxis: {
            range: [200, 300]
        }
    };

    const data = [trace1];

    Plotly.newPlot('projection', data, layout);
}

const display_trace = function() {
    const trace1 = {
      x: [1, 2, 3, 4],
      y: [10, 15, 13, 17],
      type: 'scatter'
    };

    const trace2 = {
      x: [1, 2, 3, 4],
      y: [16, 5, 11, 9],
      type: 'scatter'
    };

    const data = [trace1, trace2];

    Plotly.newPlot('trace_container', data);
}

$( document ).ready(function() {
    display_trace();
    display_projection();
});