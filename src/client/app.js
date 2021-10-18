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

class CellLabelingApp {
    constructor() {
        $.get('http://localhost:5000/get_random_roi', data => {
            this.experiment_id = data['experiment_id'];
            this.roi = data['roi'];
            console.log(data);
         }).then(() => {
            this.displayProjection();
         });
    }

    async displayProjection() {
        const projection_type = $('#projection_type').children("option:selected").val();
        const url = `http://localhost:5000/get_projection?type=${projection_type}&experiment_id=${this.experiment_id}`;
        $.get(url, async data => {
            const fovBounds = await $.post('http://localhost:5000/get_fov_bounds', JSON.stringify(this.roi));

            const trace1 = {
                source: data['projection'],
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
                    range: fovBounds['x']
                },
                yaxis: {
                    range: fovBounds['y']
                }
            };
                
            Plotly.newPlot('projection', [trace1], layout);
        })
    }    
}

$( document ).ready(function() {
    $.get('http://localhost:5000/get_random_roi', data => {
       const app = new CellLabelingApp();
    });
    display_trace();
});