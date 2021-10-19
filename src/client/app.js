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
        this.experiment_id = null;
        this.roi = null;
        this.show_current_roi_outline_on_projection = false;
        this.show_all_roi_outlines = false;
        this.projection_is_shown = false;
        this.roi_contours = null;
        this.addListeners();
    }

    addListeners() {
        $('#projection_include_mask_outline').on('click', () => {
            this.show_current_roi_outline_on_projection = !this.show_current_roi_outline_on_projection;
            this.displayContoursOnProjection();
        });

        $('#projection_include_surrounding_rois').on('click', () => {
            this.show_all_roi_outlines = !this.show_all_roi_outlines;
            this.displayContoursOnProjection();
        });

        $('#projection_type').on('change', () => {
            this.displayProjection();            
        });
    }

    async getRandomExperiment() {
        return $.get('http://localhost:5000/get_random_roi', data => {
                this.experiment_id = data['experiment_id'];
                this.roi = data['roi'];
                })
    }

    async getContours() {
        const url = `http://localhost:5000/get_roi_contours?experiment_id=${this.experiment_id}&current_roi_id=${this.roi['id']}`;
        return $.get(url, data => {
            this.roi_contours = data['contours'];
        });
    }

    async displayContoursOnProjection() {
        let roi_contours = this.roi_contours;
        
        if (!this.show_all_roi_outlines) {
            roi_contours = roi_contours.filter(x => x['id'] == this.roi['id']);
        } 
        
        if (!this.show_current_roi_outline_on_projection) {
            roi_contours = roi_contours.filter(x => x['id'] != this.roi['id']);
        }

        roi_contours = roi_contours.filter(x => x['contour'].length > 0);


        const paths = roi_contours.map(obj => {
            return obj['contour'].map((coordinate, index) => {
                let instruction;
                const [x, y] = coordinate;
                if (index == 0) {
                    instruction = `M ${x},${y}`;
                } else {
                    instruction = `L${x},${y}`;
                }

                if (index == obj['contour'].length - 1) {
                    instruction = `${instruction} Z`;
                }

                return instruction;
            });
        });
        const pathStrings = paths.map(x => x.join(' '));
        const colors = roi_contours.map(obj => {
            let color;
            if (obj['id'] == this.roi['id']) {
                color = [255, 0, 0];
            } else {
                color = obj['color'];
            }
            return color;
        });
        
        const shapes = _.zip(pathStrings, colors).map(obj => {
            const [path, color] = obj;
            return {
                type: 'polyline',
                path: path,
                opacity: 0.75,
                line: {
                  color: `rgb(${color[0]}, ${color[1]}, ${color[2]})`
                }
            }
        });

        Plotly.relayout('projection', {'shapes': shapes});

    }

    async displayProjection() {
        const projection_type = $('#projection_type').children("option:selected").val();
        const url = `http://localhost:5000/get_projection?type=${projection_type}&experiment_id=${this.experiment_id}`;
        return $.get(url, async data => {
            const fovBounds = await $.post('http://localhost:5000/get_fov_bounds', JSON.stringify(this.roi));

            const trace1 = {
                source: data['projection'],
                type: 'image'
            };
        
            if (this.projection_is_shown) {
                const layout = document.getElementById('projection').layout;
                Plotly.react('projection', [trace1], layout);
            } else {
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

                Plotly.newPlot('projection', [trace1], layout).then(() => {
                    this.projection_is_shown = true;
                });   
            }
        })
    }    
}

$( document ).ready(async function() {
    const app = new CellLabelingApp();
    await app.getRandomExperiment();
    await app.displayProjection();
    await app.getContours();

    display_trace();
});