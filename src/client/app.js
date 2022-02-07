import {
    clipImageToQuantiles,
    bytesToMatrix,
    scaleToUint8,
    toRGB,
    displayTemporaryAlert
} from './util.js';


class CellLabelingApp {
    /* Main App class */
    constructor() {
        this.displayLoginMessage();
        this.addListeners();
    }

    addListeners() {
        $('#projection_include_mask_outline').on('click', () => {
            this.show_current_region_roi_contours_on_projection = !this.show_current_region_roi_contours_on_projection;
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

        $('button#submit_labels').on('click', () => {
            this.handleSubmitRegion();
        });

        $('input#projection_contrast_low_quantile, input#projection_contrast_high_quantile').on('input', () => {
            const low = $('input#projection_contrast_low_quantile').val();
            const high = $('input#projection_contrast_high_quantile').val()
            this.updateProjectionContrast(low, high);
        });

        $('button#projection_contrast_reset').on('click', () => {
            this.resetProjectionContrast();
        });

        $('#roi-display-video-and-trace').click(() => {
            this.displayArtifacts({includeProjection: false, includeVideo: true, includeTrace: true});
        });

        $('#notes').on('input', () => {
            this.handleNotes();
        });
    }

    addProjectionListeners() {
        const projection = document.getElementById('projection');

        projection.on('plotly_click', data => {
            const point  = data.points[0];
            const [y, x] = point.pointIndex;
            this.handleProjectionClick(x, y);
        });

    }

    async getRandomRegionFromRandomExperiment() {
        const region = await $.get(`http://localhost:${PORT}/get_random_region`, data => {
            let region;
            if (data['region'] === null) {
                // No more regions to label
                window.location = `http://localhost:${PORT}/done.html`;
            } else {
                this.experiment_id = data['experiment_id'];
                this.region = data['region'];
                region = this.region;
            }
            return region;
        });
        
        if (region['region'] !== null) {
            const fovBounds = await $.post(`http://localhost:${PORT}/get_fov_bounds`, JSON.stringify(this.region));
            this.fovBounds = fovBounds;
        }

        return region;

    }

    displayTrace() {
        const url = `http://localhost:${PORT}/get_trace?experiment_id=${this.experiment_id}&roi_id=${this.selected_roi}`;

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

        if (this.discrepancy_roi_contours !== null) {
            // If we are in the state of reviewing ROIs with labels
            // that disagree with the classifier
            roi_contours = this.discrepancy_roi_contours;
        }

        if (roi_contours === null) {
            $("#projection_include_mask_outline").attr("disabled", true);
            const url = `http://localhost:${PORT}/get_roi_contours?experiment_id=${this.experiment_id}&current_region_id=${this.region['id']}`;
            await $.get(url, data => {
                roi_contours = data['contours'];
                roi_contours = roi_contours.filter(x => x['contour'].length > 0);
                this.roi_contours = roi_contours;

                $("#projection_include_mask_outline").attr("disabled", false);
                $("#projection_type").attr("disabled", false);
            });
        }

        if (!this.show_current_region_roi_contours_on_projection) {
            roi_contours = [];
        }


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
            return this.cells.has(obj['id']) ? [255, 0, 0] : obj['color'];
        });
        
        const shapes = _.zip(pathStrings, colors).map((obj, i) => {
            const [path, color] = obj;
            const line_width = roi_contours[i]['id'] === this.selected_roi ? 4 : 2;
            return {
                type: 'polyline',
                path: path,
                opacity: 1.0,
                line: {
                    width: line_width,
                    color: `rgb(${color[0]}, ${color[1]}, ${color[2]})`
                }
            }
        });

        Plotly.relayout('projection', {'shapes': shapes});
    }

    async displayProjection() {
        $('#projection-spinner').show();

        // Disable projection settings until loaded
        $('#projection_type').attr('disabled', true);
        $("#projection_include_mask_outline").attr("disabled", true);
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
                type: 'image',
                // disable hover tooltip
                hoverinfo: 'none'
            };
        
            if (this.projection_is_shown) {
                const layout = document.getElementById('projection').layout;
                Plotly.react('projection', [trace1], layout);
            } else {
                const dim = 512;
                const margin = 30;

                const layout = {
                    width: dim + margin * 2,
                    height: dim + margin * 2,
                    margin: {
                        t: margin,
                        l: margin,
                        r: margin,
                        b: margin
                    },
                    xaxis: {
                        range: this.fovBounds['x']
                    },
                    yaxis: {
                        range: this.fovBounds['y']
                    }
                };

                const config = {
                    doubleClick: false
                };

                Plotly.newPlot('projection', [trace1], layout, config).then(() => {
                    this.projection_is_shown = true;
                });
                
                this.addProjectionListeners();
            }
            
            $('#projection_type').attr('disabled', false);
            $("#projection_include_mask_outline").attr("disabled", false);
            $('#projection_contrast').attr('disabled', false);
            $('button#projection_contrast_reset').attr('disabled', false);
            $('input#projection_contrast_low_quantile').attr('disabled', false);
            $('input#projection_contrast_high_quantile').attr('disabled', false);

            await this.toggleContoursOnProjection();

            this.updateProjectionContrast();

            $('#projection-spinner').hide();
        });
    }
    
    async displayVideo({videoTimeframe = null} = {}) {
        /* Renders video
        
        Args
        -----
        - videoTimeframe:
            Start, stop of video
        */
        $('#video-spinner').show();

        // Disable contour toggle checkboxes until movie has loaded
        $('#video_include_mask_outline').attr("disabled", true);
        $('#video_include_surrounding_rois').attr('disabled', true);
        
        // Reset timestep display text
        $('#timestep_display').text('');

        // Disable goto timesteps
        $('button#trim_video_to_timeframe').attr('disabled', true);

        this.is_video_shown = false;

        if (videoTimeframe === null) {
            videoTimeframe = await fetch(`http://localhost:${PORT}/get_default_video_timeframe?experiment_id=${this.experiment_id}&roi_id=${this.selected_roi}`)
            .then(async data => await data.json())
            .then(data => data['timeframe']);
        }

        videoTimeframe = [parseInt(videoTimeframe[0]), parseInt(videoTimeframe[1])]

        const url = `http://localhost:${PORT}/get_video`;
        const postData = {
            experiment_id: this.experiment_id,
            roi_id: this.selected_roi,
            region_id: this.region['id'],
            fovBounds: this.fovBounds,
            include_current_roi_mask: this.show_current_roi_outline_on_movie,
            include_all_roi_masks: this.show_all_roi_outlines_on_movie,
            timeframe: videoTimeframe
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
                <video controls id="movie" width="512" height="512" src=${blobUrl}></video>
            `;
            $('#video_container').html($(video));

            $('#video_include_mask_outline').attr("disabled", false);
            $('#video_include_surrounding_rois').attr('disabled', false);

            if (this.is_trace_shown) {
                $('button#trim_video_to_timeframe').attr('disabled', false);
            }

            $('#timestep_display').text(`Timesteps: ${videoTimeframe[0]} - ${videoTimeframe[1]}`);

            this.is_video_shown = true;
            $('#video-spinner').hide();
        })
    }

    videoGoToTimesteps() {
        const trace = document.getElementById('trace');
        const timesteps = trace.layout.xaxis.range;

        if (timesteps[1] - timesteps[0] > 3000) {
            const msg = 'The selected timeframe is too large. Please limit to 3000 by selecting a timeframe from the trace';
            displayTemporaryAlert({msg, type: 'danger'});
            return;
        }
        this.displayVideo({videoTimeframe: timesteps});
    }

    displayArtifacts({includeProjection = true, includeVideo = false, includeTrace = false} = {}) {
        const artifactLoaders = [];
        if (includeProjection) {
            artifactLoaders.push(this.displayProjection());
        }

        if (includeVideo) {
            artifactLoaders.push(this.displayVideo());
        }

        if (includeTrace) {
            artifactLoaders.push(this.displayTrace());
        }

        return Promise.all(artifactLoaders);
    }

    initialize() {
        this.show_current_region_roi_contours_on_projection = $('#projection_include_mask_outline').is(':checked');
        this.show_current_roi_outline_on_movie = $('#video_include_mask_outline').is(':checked');
        this.show_all_roi_outlines_on_movie = $('#video_include_surrounding_rois').is(':checked');
        this.is_trace_shown = false;
        this.is_video_shown = false;
        this.roi_contours = null;
        this.discrepancy_roi_contours = null;
        this.fovBounds = null;
        this.experiment_id = null;
        this.projection_is_shown = false;
        this.projection_raw = null;
        this.region = null;
        this.is_loading_new_region = false;
        this.cells = new Set();
        this.selected_roi = null;
        this.notes = new Map();
        this.resetSideNav();

        $('button#submit_labels').attr('disabled', true);

        // Disable all the video settings (video not loaded yet)
        $('#video_include_mask_outline').attr("disabled", true);
        $('#video_include_surrounding_rois').attr("disabled", true);
        $('#trim_video_to_timeframe').attr("disabled", true);

        $('#timestep_display').text('');
    }

    async loadNewRegion() {
        $('#movie').remove();
        this.initialize();
        this.is_loading_new_region = true;
        $('#loading_text').css('display', 'inline');

        const region = await this.getRandomRegionFromRandomExperiment()
        .then(region => {
            this.is_loading_new_region = false;
            return region;
        })
        .catch(() => {
            $('#loading_text').hide();
            displayTemporaryAlert({msg: 'Error loading region', type: 'danger'});
        });
        if (region['region'] !== null) {
            return this.displayArtifacts().then(() => {
                $('button#submit_labels').attr('disabled', false);
            })
        }
    }

    submitRegion() {
        const url = `http://localhost:${PORT}/submit_region`;

        const roi_extra = Array.from(this.notes).map(x => {
            const [roi_id, notes] = x;
            return {
                roi_id,
                notes
            };
        });

        const data = {
            region_id: this.region['id'],
            labels: [
                ...Array.from(this.cells).map(x => {
                    return {
                        roi_id: x, 
                        label: 'cell'
                    }
                }),
                ...this.roi_contours
                .map(x => x['id'])
                .filter(x => !this.cells.has(x['id']))
                .map(x => {
                    return {
                        roi_id: x, 
                        label: 'not cell'
                    }
                })
            ],
            roi_extra
        };
        return $.post(url, JSON.stringify(data))
        .then(() => {
            displayTemporaryAlert({msg: 'Successfully submitted labels for region<br>Loading next region', type: 'success'});
        })
        .catch(() => {
            displayTemporaryAlert({msg: 'Error submitting labels for region', type: 'danger'});
            throw Error();
        });
    }

    displayLoginMessage() {
        $.get('/users/getCurrentUser').then(data => {
            const username = data['user_id'];
            displayTemporaryAlert({msg: `Logged in as ${username}`, type: 'info'});
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
            type: 'image',
            // disable hover tooltip 
            hoverinfo: 'none'
        };

        const layout = document.getElementById('projection').layout;

        Plotly.react('projection', [trace1], layout);
    }

    resetProjectionContrast() {
        this.updateProjectionContrast();
    }

    async handleProjectionClick(x, y) {
        /* 
        Args
        ------
        - x: x coordinate in fov of click
        - y: y coordinate in fov of click
        */
        let postData = {
            current_region_id: this.region['id'],
            roi_ids: this.roi_contours.map(roi => roi['id']),
            coordinates: [x, y]
        }
        postData = JSON.stringify(postData);
        
        
        const res = await fetch(`http://localhost:${PORT}/find_roi_at_coordinates`, 
            {   method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: postData
            }).then(response => {
                return response.json();
            });
        
        if (res['roi_id'] === null) {
            // No ROI clicked. Do nothing
            return;
        }
        
        const getClassifierProbabilityTextColor = () => {
            const labelColor = this.roi_contours.filter(x => x['id'] === res['roi_id'])[0]['color'];
            return `rgb(${labelColor.join(', ')})`
        }

        const getClassifierScore = () => {
            const score = this.roi_contours.filter(x => x['id'] === res['roi_id'])[0]['classifier_score'];
            return score.toFixed(2);
        }

        if (this.selected_roi === res['roi_id']) {
            if (this.cells.has(res['roi_id'])) {
                // Transition to "not cell"
                this.cells.delete(res['roi_id']);
                this.selected_roi = res['roi_id'];
            } else {
                // Transition to "cell"
                this.cells.add(res['roi_id']);
            }

        } else {
            // Select ROI
            this.selected_roi = res['roi_id'];
            $('#roi-sidenav #this-roi').text(`ROI ${this.selected_roi}`);
            $('#roi-sidenav > *').attr('disabled', false);
            $('#roi-sidenav #notes').attr('disabled', false);

            if (this.notes.has(this.selected_roi)) {
                $('#notes').val(this.notes.get(this.selected_roi));
            } else {
                $('#notes').val('');
            }
        }

        const labelText = this.cells.has(res['roi_id']) ? 'Cell' : 'Not Cell';
        $('#roi-sidenav #roi-label').text(labelText);
        $('#roi-sidenav #roi-classifier-score').text(`${getClassifierScore()}`)
        $('#roi-sidenav #roi-classifier-score').css('color', getClassifierProbabilityTextColor(labelText));
        
        // Redraw the contours
        this.toggleContoursOnProjection();

    }

    resetSideNav() {
        $('#roi-sidenav #this-roi').text('No ROI selected');
        $('#roi-sidenav > *').attr('disabled', true);
        $('#roi-sidenav #notes').attr('disabled', true);
        $('#roi-classifier-score').text('');
        $('#roi-label').text('');
        $('#notes').val('');

    }

    handleNotes() {
        /* Handles a notes textbox change */
        const notes = $('#notes').val();
        this.notes.set(this.selected_roi, notes);
    }

    handleSubmitRegion({userHasReviewed = false} = {}) {
        /* Handles submit labels button click 
        
        Args
        ------
        - userHasReviewed:
            Whether the user has reviewed any label-classifier 
            discrepancies and chose to ignore them
        */
        $('button#submit_labels').attr('disabled', true);

        if (!userHasReviewed) {
            const isValid = this.validateLabels();
            if (!isValid) {
                $('button#submit_labels').attr('disabled', false);
                return;
            }
        }

        this.submitRegion().then(() => {
            this.loadNewRegion();
        }).catch(e => {
            $('button#submit_labels').attr('disabled', false);
        });
    }

    validateLabels() {
        /* Flags any rois which might have been incorrectly labeled.
        Any rois with a label that disagrees with the classifier score are flagged */
        const maybeCell = this.roi_contours
            .filter(x => x['classifier_score'] >= 0.5 & !this.cells.has(x['id']));
        const maybeNotCell = this.roi_contours
            .filter(x => x['classifier_score'] < 0.5 & this.cells.has(x['id']));

        if (maybeCell.length > 0 | maybeNotCell.length > 0) {
            const msgs = [];
            const helpingVerb = count => count === 1 ? 'is' : 'are';
            const roiStr = count => count === 1 ? 'ROI' : 'ROIs';
            if (maybeCell.length > 0) {
                msgs.push(`There ${helpingVerb(maybeCell.length)} <b>${maybeCell.length}</b> 
                    ${roiStr(maybeCell.length)} labeled as "Not Cell" that the classifier thinks ${helpingVerb(maybeCell.length)} cell.`);
            }

            if (maybeNotCell.length > 0) {
                msgs.push(`There ${helpingVerb(maybeNotCell.length)} <b>${maybeNotCell.length}</b> 
                    ${roiStr(maybeNotCell.length)} labeled as "Cell" that the classifier thinks ${helpingVerb(maybeNotCell.length)} not cell.`);
            }

            const msg = msgs.join('<br><br>');

            const modalHtml = `
                <div class="modal" tabindex="-1" id="review-modal">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">Review</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close" id="review-modal-close"></button>
                            </div>
                            <div class="modal-body">
                                <p>${msg}</p>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal" id="submit-anyway">Submit anyway</button>
                                <button type="button" class="btn btn-primary" id="review">Review these ROIs</button>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            $('#modal-review-container').html(modalHtml);
            const modal = new bootstrap.Modal(document.getElementById('review-modal'));
            modal.show();

            $('#review-modal-close').click(() => {
                modal.hide();
            });

            $('#review-modal #submit-anyway').click(() => {
                this.handleSubmitRegion({userHasReviewed: true});
                modal.hide();
            });

            $('#review-modal #review').click(() => {
                this.discrepancy_roi_contours = [...maybeCell, ...maybeNotCell];
                this.toggleContoursOnProjection().then(() => {
                    modal.hide();
                });
            });

            return false;
        }

        return true;
        
    }
}

$( document ).ready(async function() {
    const app = new CellLabelingApp();
    app.loadNewRegion();
});