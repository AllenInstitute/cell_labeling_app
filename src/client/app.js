import {
    clipImageToQuantiles,
    bytesToMatrix,
    scaleToUint8,
    toRGB
} from './util.js';

import {
    LoadingIndicator
} from './loadingIndicator.js';


class CellLabelingApp {
    /* Main App class */
    constructor() {
        this.displayLoginMessage();
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

        $('button#submit_label').on('click', async () => {
            await this.submitLabel();
            this.loadNewRoi();
        });

        $('#label_cell').on('click', () => {
            $('button#submit_label').attr('disabled', false);
        });

        $('#label_not_cell').on('click', () => {
            $('button#submit_label').attr('disabled', false);
        });

        $('input#projection_contrast_low_quantile, input#projection_contrast_high_quantile').on('input', () => {
            const low = $('input#projection_contrast_low_quantile').val();
            const high = $('input#projection_contrast_high_quantile').val()
            this.updateProjectionContrast(low, high);
        });

        $('button#projection_contrast_reset').on('click', () => {
            this.resetProjectionContrast();
        })
    }

    async getRandomRoiFromRandomExperiment() {
        const roi = await $.get(`http://localhost:${PORT}/get_random_roi`, data => {
            let roi;
            if (data['roi'] === null) {
                // No more rois to label
                window.location = `http://localhost:${PORT}/done.html`;
            } else {
                this.experiment_id = data['experiment_id'];
                this.roi = data['roi'];
                roi = this.roi;
            }
            return roi;
        });
        
        if (roi['roi'] !== null) {
            const fovBounds = await $.post(`http://localhost:${PORT}/get_fov_bounds`, JSON.stringify(this.roi));
            this.fovBounds = fovBounds;
        }

        return roi;

    }

    displayTrace() {
        const url = `http://localhost:${PORT}/get_trace?experiment_id=${this.experiment_id}&roi_id=${this.roi['id']}`;
        this.loadingIndicator.add('Loading trace...');

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

            this.loadingIndicator.remove('Loading trace...');
        });
    }

    async toggleContoursOnProjection() {
        let roi_contours = this.roi_contours;

        if (roi_contours === null) {
            this.loadingIndicator.add('Loading current roi contour...');
            $("#projection_include_mask_outline").attr("disabled", true);
            const url = `http://localhost:${PORT}/get_roi_contours?experiment_id=${this.experiment_id}&current_roi_id=${this.roi['id']}&include_all_contours=false`;
            await $.get(url, data => {
                roi_contours = data['contours'];
    
                $("#projection_include_mask_outline").attr("disabled", false);
                $("#projection_type").attr("disabled", false);

                this.loadingIndicator.remove('Loading current roi contour...');
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
        
        if (this.roi_contours === null) {
            $("#projection_include_surrounding_rois").attr("disabled", true);

            // Now load all contours in background
            const url = `http://localhost:${PORT}/get_roi_contours?experiment_id=${this.experiment_id}&current_roi_id=${this.roi['id']}&include_all_contours=true`;
            this.loadingIndicator.add('Loading all roi contours...');
            return $.get(url, data => {

                // Make sure this request is not from some previous ROI
                if (!this.is_loading_new_roi && data['contours'][0]['experiment_id'] === this.roi['experiment_id']) {
                    this.roi_contours = data['contours'];

                    if (this.show_all_roi_outlines_on_projection) {
                        this.toggleContoursOnProjection();
                    }
                    $("#projection_include_surrounding_rois").attr("disabled", false);
                    this.loadingIndicator.remove('Loading all roi contours...');
                }
            });
        }

        return;
    }

    async displayProjection() {
        this.loadingIndicator.add('Loading projection...');

        // Disable projection settings until loaded
        $('#projection_type').attr('disabled', true);
        $("#projection_include_mask_outline").attr("disabled", true);
        $("#projection_include_surrounding_rois").attr("disabled", true);
        $('#projection_contrast').attr('disabled', true);
        $('button#projection_contrast_reset').attr('disabled', true);
        $('input#projection_contrast_low_quantile').attr('disabled', true);
        $('input#projection_contrast_high_quantile').attr('disabled', true);


        // reset projection contrast
        $('input#projection_contrast').val(100);
        $('#projection_contrast_label').text(`Contrast: 100%`);

        const projection_type = $('#projection_type').children("option:selected").val();
        const url = `http://localhost:${PORT}/get_projection?type=${projection_type}&experiment_id=${this.experiment_id}`;
        return fetch(url).then(async data => {
            const blob = await data.blob();
            data = await bytesToMatrix(blob);
            
            data = data._data;
            this.projection_raw = data;
            
            if (projection_type !== 'correlation') {
                data = scaleToUint8(data);
            }

            data = toRGB(data);
        
            const trace1 = {
                z: data,
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
            
            $('#projection_type').attr('disabled', false);
            $("#projection_include_mask_outline").attr("disabled", false);
            $('#projection_contrast').attr('disabled', false);
            $('button#projection_contrast_reset').attr('disabled', false);
            $('input#projection_contrast_low_quantile').attr('disabled', false);
            $('input#projection_contrast_high_quantile').attr('disabled', false);

            if (this.roi_contours !== null) {
                $("#projection_include_surrounding_rois").attr("disabled", false);
            }

            this.loadingIndicator.remove('Loading projection...');

            this.toggleContoursOnProjection().then(() => {
                $("#projection_include_surrounding_rois").attr("disabled", false);
            });

            this.updateProjectionContrast();
        });
    }
    
    async displayVideo() {
        this.loadingIndicator.add('Loading video...');

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
            await fetch(`http://localhost:${PORT}/get_default_video_timeframe?experiment_id=${this.experiment_id}&roi_id=${this.roi['id']}`)
            .then(async data => await data.json())
            .then(data => {
                videoTimeframe = data['timeframe'];
            });
        }

        this.videoTimeframe = [parseInt(videoTimeframe[0]), parseInt(videoTimeframe[1])]

        const url = `http://localhost:${PORT}/get_video`;
        const postData = {
            experiment_id: this.experiment_id,
            roi_id: this.roi['id'],
            fovBounds: this.fovBounds,
            include_current_roi_mask: this.show_current_roi_outline_on_movie,
            include_all_roi_masks: this.show_all_roi_outlines_on_movie,
            timeframe: this.videoTimeframe
        };
        return $.ajax({
            xhrFields: {
               responseType: 'blob' 
            },
            type: 'POST',
            url: url,
            data: JSON.stringify(postData)
        }).then(response => {
            const blob = new Blob([response], {type: "video\/mp4"});
            const blobUrl = URL.createObjectURL(blob);
            const video = `
                <video controls id="movie" width="452" height="452" src=${blobUrl}></video>
            `;
            $('#video_container').html($(video));

            $('#video_include_mask_outline').attr("disabled", false);
            $('#video_include_surrounding_rois').attr('disabled', false);

            if (this.is_trace_shown) {
                $('button#trim_video_to_timeframe').attr('disabled', false);
            }

            $('#timestep_display').text(`Timesteps: ${this.videoTimeframe[0]} - ${this.videoTimeframe[1]}`);

            this.is_video_shown = true;
            this.loadingIndicator.remove('Loading video...');
        })
    }

    videoGoToTimesteps() {
        const trace = document.getElementById('trace');
        const timesteps = trace.layout.xaxis.range;

        if (timesteps[1] - timesteps[0] > 3000) {
            let alert = `
                <div class="alert alert-danger fade show" role="alert" style="margin-top: 20px" id="alert-error">
                    The selected timeframe is too large. Please limit to 3000 by selecting a timeframe from the trace
                </div>`;
            alert = $(alert);

            alert.insertBefore($('#label_bar'));
            
            setTimeout(() => $('#alert-error').alert('close'), 10000);
            return;
        }
        this.videoTimeframe = timesteps;
        this.displayVideo();
    }

    displayArtifacts() {
        return Promise.all([
            this.displayVideo(),
            this.displayProjection(),
            this.displayTrace()
        ]);
    }

    initialize() {
        this.show_current_roi_outline_on_projection = $('#projection_include_mask_outline').is(':checked');
        this.show_all_roi_outlines_on_projection = $('#projection_include_surrounding_rois').is(':checked');
        this.show_current_roi_outline_on_movie = $('#video_include_mask_outline').is(':checked');
        this.show_all_roi_outlines_on_movie = $('#video_include_surrounding_rois').is(':checked');
        this.is_trace_shown = false;
        this.is_video_shown = false;
        this.roi_contours = null;
        this.fovBounds = null;
        this.videoTimeframe = null;
        this.experiment_id = null;
        this.projection_is_shown = false;
        this.projection_raw = null;
        this.roi = null;
        this.is_loading_new_roi = false;
        this.loadingIndicator = new LoadingIndicator();

        $('button#submit_label').attr('disabled', true);
    }

    async loadNewRoi() {
        $('#movie').remove();
        this.initialize();
        this.is_loading_new_roi = true;
        $('#loading_text').css('display', 'inline');

        const roi = await this.getRandomRoiFromRandomExperiment()
        .then(roi => {
            this.is_loading_new_roi = false;
            return roi;
        })
        .catch(() => {
            $('#loading_text').hide();

            let alert = `
                <div class="alert alert-danger fade show" role="alert" style="margin-top: 20px" id="alert-error">
                    Error loading ROI
                </div>`;
            alert = $(alert);

            alert.insertBefore($('#label_bar'));
            
            setTimeout(() => $('#alert-error').alert('close'), 10000);
        });
        if (roi['roi'] !== null) {
            this.displayArtifacts();
        }
    }

    submitLabel() {
        const url = `http://localhost:${PORT}/add_label`;
        const label = $('#label_cell').is(':checked') === true ? 'cell' : 'not cell';
        const data = {
            experiment_id: this.experiment_id,
            roi_id: this.roi['id'],
            label: label
        };
        this.loadingIndicator.add('Submitting...');
        return $.post(url, JSON.stringify(data)).then(() => {
            $('#label_cell').prop('checked', false);
            $('#label_not_cell').prop('checked', false);
            this.loadingIndicator.remove('Submitting...');
        })
    }

    displayLoginMessage() {
        $.get('/users/getCurrentUser').then(data => {
            const username = data['user_id'];
            let alert = `
                <div class="alert alert-info fade show" role="alert" style="margin-top: 20px" id="alert-error">
                    Logged in as ${username}
                </div>`;
            alert = $(alert);

            alert.insertBefore($('#label_bar'));
            
            setTimeout(() => $('#alert-error').alert('close'), 5000);
        });
    }

    updateProjectionContrast(low = 0.0, high = 1.0) {
        $('input#projection_contrast_low_quantile').val(low);
        $('input#projection_contrast_high_quantile').val(high);

        $('#projection_contrast_low_quantile_label').text(`Low quantile: ${low}`);
        $('#projection_contrast_high_quantile_label').text(`High quantile: ${high}`);

        let x = clipImageToQuantiles(this.projection_raw, low, high);
        x = scaleToUint8(x);
        x = toRGB(x);

        const trace1 = {
            z: x,
            type: 'image'
        };

        const layout = document.getElementById('projection').layout;

        Plotly.react('projection', [trace1], layout);
    }

    resetProjectionContrast() {
        this.updateProjectionContrast();
    }
}

$( document ).ready(async function() {
    const app = new CellLabelingApp();
    app.loadNewRoi();
});