class CellLabelingApp {
    constructor() {
        this.experiment_id = null;
        this.roi = null;
        this.show_current_roi_outline_on_projection = true;
        this.show_all_roi_outlines_on_projection = false;
        this.show_current_roi_outline_on_movie = true;
        this.show_all_roi_outlines_on_movie = false;
        this.projection_is_shown = false;
        this.is_trace_shown = false;
        this.is_video_shown = false;
        this.roi_contours = null;
        this.fovBounds = null;
        this.videoTimeframe = null;

        // Disable contour toggle checkboxes until contours have loaded
        $("#projection_include_mask_outline").attr("disabled", true);
        $("#projection_include_surrounding_rois").attr("disabled", true);

        this.addListeners();
    }

    addListeners() {
        $('#projection_include_mask_outline').on('click', () => {
            this.show_current_roi_outline_on_projection = !this.show_current_roi_outline_on_projection;
            this.toggleContoursOnProjection();
        });

        $('#projection_include_surrounding_rois').on('click', () => {
            this.show_all_roi_outlines_on_projection = !this.show_all_roi_outlines_on_projection;
            this.toggleContoursOnProjection();
        });

        $('#projection_type').on('change', () => {
            this.displayProjection();            
        });

        $('#video_include_mask_outline').on('click', () => {
            this.show_current_roi_outline_on_movie = !this.show_current_roi_outline_on_movie;
            this.displayVideo();
        });

        $('#video_include_surrounding_rois').on('click', () => {
            this.show_all_roi_outlines_on_movie = !this.show_all_roi_outlines_on_movie;
            this.displayVideo();
        });

        $('button#trim_video_to_timeframe').on('click', () => {
            this.videoGoToTimesteps();
        });
    }

    async getRandomRoiFromRandomExperiment() {
        return $.get('http://localhost:5000/get_random_roi', data => {
                this.experiment_id = data['experiment_id'];
                this.roi = data['roi'];
                }).then(async () => {
                    const fovBounds = await $.post('http://localhost:5000/get_fov_bounds', JSON.stringify(this.roi));
                    this.fovBounds = fovBounds;
                })
    }

    displayTrace() {
        const url = `http://localhost:5000/get_trace?experiment_id=${this.experiment_id}&roi_id=${this.roi['id']}`;
        return $.get(url, data => {
            const trace = {
                x: _.range(data['trace'].length),
                y: data['trace']
            }

            const layout = {
                xaxis: {
                    title: 'Timestep'
                },
                yaxis: {
                    title: 'Trace magnitude'
                }
            }

            Plotly.newPlot('trace', [trace], layout);

            this.is_trace_shown = true;

            // Enable this button if not already enabled
            if (this.is_video_shown) {
                $('button#trim_video_to_timeframe').attr('disabled', false);
            }
        });
    }

    async toggleContoursOnProjection() {
        let roi_contours = this.roi_contours;

        if (roi_contours === null) {
            const url = `http://localhost:5000/get_roi_contours?experiment_id=${this.experiment_id}&current_roi_id=${this.roi['id']}&include_all_contours=false`;
            await $.get(url, data => {
                roi_contours = data['contours'];
    
                $("#projection_include_mask_outline").attr("disabled", false);
            });
        }
        
        if (!this.show_all_roi_outlines_on_projection) {
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

        // Now load all contours in background
        const url = `http://localhost:5000/get_roi_contours?experiment_id=${this.experiment_id}&current_roi_id=${this.roi['id']}&include_all_contours=true`;
        $.get(url, data => {
            this.roi_contours = data['contours'];
            $("#projection_include_surrounding_rois").attr("disabled", false);
        })

    }

    async displayProjection() {
        const projection_type = $('#projection_type').children("option:selected").val();
        const url = `http://localhost:5000/get_projection?type=${projection_type}&experiment_id=${this.experiment_id}`;
        return $.get(url, async data => {
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
                        range: this.fovBounds['x']
                    },
                    yaxis: {
                        range: this.fovBounds['y']
                    }
                };

                Plotly.newPlot('projection', [trace1], layout).then(() => {
                    this.projection_is_shown = true;
                });
            }

            this.toggleContoursOnProjection(); 
        })
    }
    
    async displayVideo() {
        // Disable contour toggle checkboxes until movie has loaded
        $('#video_include_mask_outline').attr("disabled", true);
        $('#video_include_surrounding_rois').attr('disabled', true);
        
        // Reset timestep display text
        $('#timestep_display').text('');

        // Disable goto timesteps
        $('button#trim_video_to_timeframe').attr('disabled', true);

        this.is_video_shown = false;

        let videoTimeframe = this.videoTimeframe;

        if (videoTimeframe === null) {
            await fetch(`http://localhost:5000/get_default_video_timeframe?experiment_id=${this.experiment_id}&roi_id=${this.roi['id']}`)
            .then(data => data.json())
            .then(data => {
                videoTimeframe = data['timeframe'];
            });
        }

        this.videoTimeframe = [parseInt(videoTimeframe[0]), parseInt(videoTimeframe[1])]

        const url = `http://localhost:5000/get_video`;
        const postData = {
            experiment_id: this.experiment_id,
            roi_id: this.roi['id'],
            fovBounds: this.fovBounds,
            include_current_roi_mask: this.show_current_roi_outline_on_movie,
            include_all_roi_masks: this.show_all_roi_outlines_on_movie,
            timeframe: this.videoTimeframe
        };
        $.ajax({
            xhrFields: {
               responseType: 'blob' 
            },
            type: 'POST',
            url: url,
            data: JSON.stringify(postData)
        }).then(response => {
            const blob = new Blob([response], {type: "video\/mp4"});
            const blobUrl = URL.createObjectURL(blob);
            $('#movie').attr("src", blobUrl);

            $('#video_include_mask_outline').attr("disabled", false);
            $('#video_include_surrounding_rois').attr('disabled', false);

            if (this.is_trace_shown) {
                $('button#trim_video_to_timeframe').attr('disabled', false);
            }

            $('#timestep_display').text(`Timesteps: ${this.videoTimeframe[0]} - ${this.videoTimeframe[1]}`);

            this.is_video_shown = true;
        })
    }

    videoGoToTimesteps() {
        const trace = document.getElementById('trace');
        const timesteps = trace.layout.xaxis.range;
        this.videoTimeframe = timesteps;
        this.displayVideo();
    }

    displayArtifacts() {
        this.displayVideo();
        this.displayProjection();
        this.displayTrace();
    }
}

$( document ).ready(async function() {
    const app = new CellLabelingApp();
    await app.getRandomRoiFromRandomExperiment();
    app.displayArtifacts();
});