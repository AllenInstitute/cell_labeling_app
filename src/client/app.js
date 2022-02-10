import {
    clipImageToQuantiles,
    bytesToMatrix,
    scaleToUint8,
    toRGB,
    displayTemporaryAlert
} from './util.js';

import {
    ROI
} from './roi.js';


class CellLabelingApp {
    /* Main App class */
    constructor() {
        this.displayLoginMessage();
        this.addListeners();
    }

    addListeners() {
        $('#projection_include_mask_outline').on('click', async () => {
            this.show_current_region_roi_contours_on_projection = !this.show_current_region_roi_contours_on_projection;
            await this.updateShapesOnProjection();
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
        const url = `http://localhost:${PORT}/get_trace?experiment_id=${this.experiment_id}&roi_id=${this.selected_roi.id}&is_segmented=${this.selected_roi.contour !== null}`;

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
        let rois = this.rois;

        if (this.discrepancy_rois !== null) {
            // If we are in the state of reviewing ROIs with labels
            // that disagree with the classifier
            rois = this.discrepancy_rois;
        }

        if (rois === null) {
            $("#projection_include_mask_outline").attr("disabled", true);
            const url = `http://localhost:${PORT}/get_roi_contours?experiment_id=${this.experiment_id}&current_region_id=${this.region['id']}`;
            await $.get(url, data => {
                rois = data['contours'].map(x => new ROI({
                    id: x['id'],
                    experiment_id: x['experiment_id'],
                    color: x['color'],
                    classifier_score: x['classifier_score'],
                    label: 'not cell',
                    contour: x['contour']
                }));
                rois = rois.filter(x => x.contour.length > 0);
                this.rois = rois;

                $("#projection_include_mask_outline").attr("disabled", false);
                $("#projection_type").attr("disabled", false);
            });
        }

        if (!this.show_current_region_roi_contours_on_projection) {
            rois = [];
        }

        rois = rois.filter(x => x.contour !== null);

        const paths = rois.map(obj => {
                return obj.contour.map((coordinate, index) => {
                    let instruction;
                    const [x, y] = coordinate;
                    if (index === 0) {
                        instruction = `M ${x},${y}`;
                    } else {
                        instruction = `L${x},${y}`;
                    }

                    if (index === obj['contour'].length - 1) {
                        instruction = `${instruction} Z`;
                    }

                    return instruction;
                });
        });
        const pathStrings = paths.map(x => x.join(' '));
        const colors = rois.map(obj => {
            return obj.label === 'cell' ? [255, 0, 0] : obj.color;
        });
        
        const shapes = _.zip(pathStrings, colors).map((obj, i) => {
            const [path, color] = obj;
            let line_width = 2;
            if(this.selected_roi !== null && rois[i].id === this.selected_roi.id) {
                line_width = 4;
            }
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

            await this.updateShapesOnProjection();

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
            videoTimeframe = await fetch(`http://localhost:${PORT}/get_default_video_timeframe?experiment_id=${this.experiment_id}&roi_id=${this.selected_roi.id}&is_segmented=${this.selected_roi.contour !== null}`)
            .then(async data => await data.json())
            .then(data => data['timeframe']);
        }

        videoTimeframe = [parseInt(videoTimeframe[0]), parseInt(videoTimeframe[1])]

        const url = `http://localhost:${PORT}/get_video`;
        const postData = {
            experiment_id: this.experiment_id,
            roi_id: this.selected_roi.id,
            point: this.selected_roi.point,
            color: this.selected_roi.color,
            region_id: this.region['id'],
            fovBounds: this.fovBounds,
            include_current_roi_mask: this.show_current_roi_outline_on_movie,
            include_all_roi_masks: this.show_all_roi_outlines_on_movie,
            timeframe: videoTimeframe,
            is_segmented: this.selected_roi.contour !== null,
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

    displayROIPointsOnProjection(radius = 2) {
        let rois;
        if (!this.show_current_region_roi_contours_on_projection) {
            rois = [];
        } else {
            rois = this.rois;
        }
        const points = rois
            // Filter out all segmented ROIs to leave just the points
            .filter(x => x.contour === null)
            .map(roi => {
                const [x, y] = roi.point;
                return {
                    type: 'circle',
                    opacity: 1.0,
                    fillcolor: `rgb(${roi.color.join(',')})`,
                    x0: x - radius,
                    x1: x + radius,
                    y0: y - radius,
                    y1: y + radius
                }

            });

        const contours = document.getElementById('projection').layout.shapes
            .filter(x => x['type'] !== 'circle');
        const shapes = [...contours, ...points];
        Plotly.relayout('projection', {'shapes': shapes});
    }

    initialize() {
        this.show_current_region_roi_contours_on_projection = $('#projection_include_mask_outline').is(':checked');
        this.show_current_roi_outline_on_movie = $('#video_include_mask_outline').is(':checked');
        this.show_all_roi_outlines_on_movie = $('#video_include_surrounding_rois').is(':checked');
        this.is_trace_shown = false;
        this.is_video_shown = false;
        this.rois = null;
        this.discrepancy_rois = null;
        this.fovBounds = null;
        this.experiment_id = null;
        this.projection_is_shown = false;
        this.projection_raw = null;
        this.region = null;
        this.is_loading_new_region = false;
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
                this.rois.map(x => {
                    return {
                        roi_id: x.id,
                        is_segmented: x.contour !== null,
                        point: x.point, 
                        label: x.label
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
            roi_ids: this.rois.map(roi => roi.id),
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
            this.#handleNonSegmentedPointClick({x, y});
        } else {
            await this.#handleSegmentedPointClick({roi_id: res['roi_id']});
        }
    }

    async #handleSegmentedPointClick({roi_id} = {}) {
        /* Handles when the user clicks on a point with a computed boundary */
        const selectedRoi = this.rois.find(x => x.id == roi_id)

        const cell_roi_ids = new Set(
            this.rois.filter(x => x.label === 'cell')
            .map(x => x.id)
        );

        if (this.selected_roi !== null && this.selected_roi.id === selectedRoi.id) {
            const idx = this.rois.findIndex(x => x.id === selectedRoi.id);
            // Clicking the currently selected ROI again
            if (cell_roi_ids.has(selectedRoi.id)) {
                // Transition to "not cell"
                this.rois[idx].label = 'not cell';
                this.selected_roi = selectedRoi;
            } else {
                // Transition to "cell"
                this.rois[idx].label = 'cell';
            }

        } else {
            // Select a new ROI
            this.selected_roi = selectedRoi;
        }
        
        this.#updateSideNav();

        // Redraw the contours
        await this.toggleContoursOnProjection();
    }

    #handleNonSegmentedPointClick({x, y} = {}) {
        /* Handles when the user clicks on a point that has no computed boundary 
        Args
        ------
        - x: x coordinate in fov of click
        - y: y coordinate in fov of click
        */
        const isClose = (point1, point2) => {
            /* Returns true if the newly selected point is 
            close to the currently selected point 
        
            Args
            -----
            */
            const [x1, y1] = point1;
            const [x2, y2] = point2;
            const distance = Math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2);
            return distance <= 4;
        }
       const closePointIdx = this.rois
           .findIndex(roi => roi.point !== null &&
                      isClose(roi.point, [x, y]));
        let selectedRoi;
       if (closePointIdx >= 0) {
           // Clicking on a point that already exists
           selectedRoi = this.rois[closePointIdx];
           if (this.rois[closePointIdx].label === 'cell') {
               this.rois[closePointIdx].label = 'not cell';
               this.rois[closePointIdx].color = [255, 255, 255]
           } else {
               this.rois[closePointIdx].label = 'cell';
               this.rois[closePointIdx].color = [255, 0, 0]
           }

       } else {
           // Clicking on a new point
           selectedRoi = new ROI({
               id: `${x},${y}`,
               experiment_id: this.experiment_id,
               color: [255, 255, 255],
               label: 'not cell',
               point: [x, y]
           });
           this.rois.push(selectedRoi);
       }

       if (this.selected_roi !== null &&
           this.selected_roi.label === 'not cell' &&
           this.selected_roi.id !== selectedRoi.id) {
           // If we had an ROI selected and it is not a cell, and it is not the current roi,
           // remove it
           this.rois = this.rois.filter(x => x.id !== this.selected_roi.id);
        }

       this.selected_roi = selectedRoi;

        this.resetSideNav();
        this.#updateSideNav();
        this.displayROIPointsOnProjection();
    }

    #updateSideNav() {
        /* Updates the sidenav because a new point has been clicked */ 
        const point = this.selected_roi.point;
        const roi_id = this.selected_roi.id;
        const isSegmented = this.selected_roi.contour !== null;
        const roiText = isSegmented ? `ROI ${roi_id}` : `ROI at point ${point}`;
        $('#roi-sidenav #this-roi').text(roiText);
        $('#roi-sidenav > *').attr('disabled', false);
        $('#roi-sidenav #notes').attr('disabled', false);
        
        if (this.notes.has(roi_id)) {
            $('#notes').val(this.notes.get(roi_id));
        } else {
            $('#notes').val('');
        }

        const getClassifierScore = () => {
            const score = this.rois.filter(x => x.id === roi_id)[0]['classifier_score'];
            return score.toFixed(2);
        }

        const getClassifierProbabilityTextColor = () => {
            const labelColor = this.rois.filter(x => x.id === roi_id)[0]['color'];
            return `rgb(${labelColor.join(', ')})`
        }

        const labelText = this.rois.find(x => x.id === roi_id).label === 'cell' ? 'Cell' : 'Not Cell';
        $('#roi-sidenav #roi-label').text(labelText);

        if (this.selected_roi.contour !== null) {
            $('#roi-sidenav #roi-classifier-score').text(`${getClassifierScore()}`)
            $('#roi-sidenav #roi-classifier-score').css('color', getClassifierProbabilityTextColor(labelText));
        }

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
        this.notes.set(this.selected_roi.id, notes);
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
        const maybeCell = this.rois
            .filter(x => x.classifier_score >= 0.5 & !x.label !== 'cell');
        const maybeNotCell = this.rois
            .filter(x => x.classifier_score < 0.5 & x.label === 'cell');

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
                this.discrepancy_rois = [...maybeCell, ...maybeNotCell];
                this.updateShapesOnProjection().then(() => {
                    modal.hide();
                });
            });

            return false;
        }

        return true;
        
    }

    async updateShapesOnProjection() {
        await this.toggleContoursOnProjection();
        this.displayROIPointsOnProjection();
    }
}

$( document ).ready(async function() {
    const app = new CellLabelingApp();
    app.loadNewRegion();
});