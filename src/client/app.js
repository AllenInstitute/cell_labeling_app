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
    constructor({field_of_view_dims}={}) {
        this.fieldOfViewDims = field_of_view_dims;
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
            this.displayArtifacts({
                includeProjection: false,
                includeVideo: true,
                includeTrace: true
            });
        });

        $('#notes').on('input', () => {
            this.handleNotes();
        });

        $('#nav-review').on('click', () => {
            this.#handleReviewNavClick();
        })
    }

    addProjectionListeners() {
        const projection = document.getElementById('projection');

        projection.on('plotly_click', data => {
            const point = data.points[0];
            const [y, x] = point.pointIndex;
            this.handleProjectionClick(x, y);
        });

    }

    displayTrace() {
        const url = `http://localhost:${PORT}/get_trace?experiment_id=${this.experiment_id}&roi_id=${this.selected_roi.id}&is_segmented=${this.selected_roi.contours !== null}`;

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
                    title: 'Trace magnitude',
                    // Prevent zoom event on y axis
                    fixedrange: true
                }
            }

            const config = {
                responsive: true
            }

            Plotly.newPlot('trace', [trace], layout, config);

            this.is_trace_shown = true;

            // Enable this button if not already enabled
            if (this.is_video_shown) {
                $('button#trim_video_to_timeframe').attr('disabled', false);
            }
        });
    }

    async getRoiContourShapes() {
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
                    contours: x['contours']
                }));
                rois = rois.filter(x => x.contours.length > 0);
                this.rois = rois;

                $("#projection_include_mask_outline").attr("disabled", false);
                $("#projection_type").attr("disabled", false);
            });
        }

        if (!this.show_current_region_roi_contours_on_projection) {
            rois = [];
        }

        rois = rois.filter(x => x.contours !== null);

        const paths = rois.map(obj => {
            let instructions = obj.contours.map(contours => {
                return contours.map((coordinate, index) => {
                    let instruction;
                    const [x, y] = coordinate;
                    if (index === 0) {
                        instruction = `M ${x},${y}`;
                    } else {
                        instruction = `L${x},${y}`;
                    }

                    return instruction;
                });
            });
            // Flatten multiple contours into single instruction set
            instructions = _.flatten(instructions);

            // Add the end instruction
            instructions.push('Z');
            return instructions;
        });
        const pathStrings = paths.map(x => x.join(' '));
        const colors = rois.map(obj => {
            return obj.label === 'cell' ? [255, 0, 0] : obj.color;
        });

        return _.zip(pathStrings, colors).map((obj, i) => {
            const [path, color] = obj;
            let line_width = 2;
            if (this.selected_roi !== null && rois[i].id === this.selected_roi.id) {
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
    }

    async displayProjection() {
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
            videoTimeframe = await fetch(`http://localhost:${PORT}/get_default_video_timeframe?experiment_id=${this.experiment_id}&roi_id=${this.selected_roi.id}&is_segmented=${this.selected_roi.contours !== null}`)
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
            is_segmented: this.selected_roi.contours !== null,
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

    displayArtifacts({
                         includeProjection = true,
                         includeVideo = false,
                         includeTrace = false
                     } = {}) {
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

    getRoiPointShapes(radius = 2) {
        let rois;
        if (!this.show_current_region_roi_contours_on_projection) {
            rois = [];
        } else {
            rois = this.rois;
        }
        const points = rois
            // Filter out all segmented ROIs to leave just the points
            .filter(x => x.contours === null)
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
        return points;
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
        this.labelingStart = Date.now();
        this.resetSideNav();

        $('button#submit_labels').attr('disabled', true);

        // Disable all the video settings (video not loaded yet)
        $('#video_include_mask_outline').attr("disabled", true);
        $('#video_include_surrounding_rois').attr("disabled", true);
        $('#trim_video_to_timeframe').attr("disabled", true);

        $('#timestep_display').text('');

        // Initialize contrast controls
        const contrast = this.#getContrastValues();
        this.#updateContrastControls(contrast);
    }

    async loadNewRegion(region_id = null) {
        $('#projection-spinner').show();
        $('#movie').remove();
        this.initialize();
        $('#loading_text').css('display', 'inline');

        let region;
        try {
            if (region_id === null) {
                this.#populateSubmittedRegionsTable();
                region = await $.get(`http://localhost:${PORT}/get_random_region`, data => {
                    if (data['region'] === null) {
                        // No more regions to label
                        window.location = `http://localhost:${PORT}/done.html`;
                    }
                });
            } else {
                region = await fetch(`http://localhost:${PORT}/get_region?region_id=${region_id}`)
                    .then(res => res.json());
            }
        } catch (e) {
            $('#loading_text').hide();
            displayTemporaryAlert({
                msg: 'Error loading region',
                type: 'danger'
            });
            $('#projection-spinner').hide();
            return;
        }

        this.region = region['region'];
        this.experiment_id = region['experiment_id'];

        const promises = [
            $.post(`http://localhost:${PORT}/get_fov_bounds`, JSON.stringify(region['region'])),
            fetch(`http://localhost:${PORT}/get_motion_border?experiment_id=${this.experiment_id}`
                ).then(data => data.json())
        ]

        const [fovBounds, motionBorder] = await Promise.all(promises);
        this.fovBounds = fovBounds;
        this.motionBorder = motionBorder;

        if (region['region'] !== null) {
            return this.displayArtifacts().then(() => {
                $('#projection-spinner').hide();
                $('#region_meta').html(
                    `Experiment id: ${this.experiment_id} | Region id: ${this.region['id']}`);
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
            labels:
                this.rois
                    // Filtering out any currently selected non-cell points
                    .filter(x => x.contours !== null ||
                        (x.point !== null && x.label === 'cell'))
                    .map(x => {
                        return {
                            roi_id: x.id,
                            is_segmented: x.contours !== null,
                            point: x.point,
                            label: x.label
                        }
                    }),
            roi_extra,
            duration: (Date.now() - this.labelingStart) / 1000
        };
        return $.post(url, JSON.stringify(data))
            .then(async () => {
                // Update labeler stats
                const statsHtml = await fetch(
                    `http://localhost:${PORT}/get_label_stats`
                )
                    .then(data => data.json())
                    .then(stats => {
                        const total = stats['n_total'];
                        const completed = stats['n_completed'];
                        const userLabeled = stats['n_user_has_labeled'];
                        const html = `
                            <p>
                                You have labeled
                                <span class="label_stats">${userLabeled}</span> ${userLabeled > 1 || userLabeled === 0 ? 'regions' : 'region'}
                                and there are <span class="label_stats">${total - userLabeled - completed}</span> remaining
                            </p>`;
                        return html;
                    }
                );
                const msg = `Successfully submitted labels for region<br>Loading next region<br>${statsHtml}`;
                displayTemporaryAlert({
                    msg,
                    type: 'success'
                });
            })
            .catch(() => {
                displayTemporaryAlert({
                    msg: 'Error submitting labels for region',
                    type: 'danger'
                });
                throw Error();
            });
    }

    displayLoginMessage() {
        $.get('/users/getCurrentUser').then(data => {
            const username = data['user_id'];
            displayTemporaryAlert({
                msg: `Logged in as ${username}`,
                type: 'info'
            });
        });
    }

    updateProjectionContrast(low = null, high = null) {
        low = parseFloat(low);
        high = parseFloat(high);
        const contrast = this.#getContrastValues(low, high);
        const projection_type = $('#projection_type').children("option:selected").val();
        Cookies.set('contrast', JSON.stringify({
                ...JSON.parse(Cookies.get('contrast') ? Cookies.get('contrast') : null),
                [projection_type]: contrast
        }));

        this.#updateContrastControls(contrast);

        let x = clipImageToQuantiles(this.projection_raw, contrast.low, contrast.high);
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

    #updateContrastControls(contrast) {
        /* Updates the contrast controls. Contrast should be an object with
        properties `low` and `high`. */
        $('input#projection_contrast_low_quantile').val(contrast.low);
        $('input#projection_contrast_high_quantile').val(contrast.high);

        $('#projection_contrast_low_quantile_label').text(`Low quantile: ${contrast.low}`);
        $('#projection_contrast_high_quantile_label').text(`High quantile: ${contrast.high}`);
    }

    #getContrastValues(low = null, high = null) {
        /* Tries to get contrast from cookie if a value for `low` and `high`
        are not given. Otherwise returns default values.  */
        let contrast;
        const projection_type = $('#projection_type').children("option:selected").val();
        if ((low === null && high === null) || (math.isNaN(low)) && math.isNaN(high)) {
            contrast = this.#getSavedContrastValuesForProjectionType({projection_type});
            if (contrast === null) {
                contrast = {
                    low: 0.0,
                    high: 1.0
                }
            }
        } else {
            contrast = {
                low,
                high
            }
        }

        return contrast;
    }

    #getSavedContrastValuesForProjectionType({projection_type}={}) {
        /* Tries to get saved contrast values for a particular projection type.
        Returns null if there are none.
         */
        let contrast = Cookies.get('contrast');
        if (contrast !== undefined) {
            contrast = JSON.parse(contrast);
            if (contrast.hasOwnProperty(projection_type)) {
                return contrast[projection_type];
            }
        }
        return null;
    }

    resetProjectionContrast() {
        this.updateProjectionContrast(0.0, 1.0);
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
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: postData
            }).then(response => {
            return response.json();
        });

        if (res['roi_id'] === null) {
            await this.#handleNonSegmentedPointClick({x, y});
        } else {
            await this.#handleSegmentedPointClick({roi_id: res['roi_id']});
        }
    }

    async #handleSegmentedPointClick({roi_id} = {}) {
        /* Handles when the user clicks on a point with a computed boundary */
        const selectedRoi = this.rois.find(x => x.id === roi_id)

        const cell_roi_ids = new Set(
            this.rois.filter(x => x.label === 'cell')
                .map(x => x.id)
        );

        this.removeCurrentlySelectedNonSegmentedPoint(selectedRoi);

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
        await this.updateShapesOnProjection();
    }

    async #handleNonSegmentedPointClick({x, y} = {}) {
        /* Handles when the user clicks on a point that has no computed boundary 
        Args
        ------
        - x: x coordinate in fov of click
        - y: y coordinate in fov of click
        */

        // Checking if clicked point is outside requested region
        // Note x and y swapped due to image coordinates
        if (x < this.region.y || x > this.region.y + this.region.height ||
            y < this.region.x || y > this.region.x + this.region.width) {
            const msg = 'The clicked point is outside of the requested region';
            displayTemporaryAlert({msg, type: 'danger'});
            return;
        }
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

        this.removeCurrentlySelectedNonSegmentedPoint(selectedRoi);

        this.selected_roi = selectedRoi;

        this.resetSideNav();
        this.#updateSideNav();
        await this.updateShapesOnProjection();
    }

    #updateSideNav() {
        /* Updates the sidenav because a new point has been clicked */
        const point = this.selected_roi.point;
        const roi_id = this.selected_roi.id;
        const isSegmented = this.selected_roi.contours !== null;
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
        if (labelText === 'Cell') {
            $('#roi-sidenav #roi-label').css('color', 'red');
        } else {
            $('#roi-sidenav #roi-label').css('color', 'black');
        }

        if (this.selected_roi.contours !== null) {
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
            .filter(x => x.classifier_score >= 0.5 & x.label !== 'cell');
        const maybeNotCell = this.rois
            .filter(x => x.classifier_score < 0.5 & x.label === 'cell');

        if (maybeCell.length > 0 || maybeNotCell.length > 0) {
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

    getRegionBoundariesShape() {
        return {
            type: 'rect',
            opacity: 0.75,
            line: {
                color: 'rgb(255, 255, 255)'
            },
            y0: this.region.x,
            y1: this.region.x + this.region.height,
            x0: this.region.y,
            x1: this.region.y + this.region.width
        }
    }

    async getMotionBorderShape() {
        const mb = this.motionBorder;
        const sides = ['left_side', 'right_side', 'top', 'bottom'];

        return sides.map(side => {
            let x0, x1, y0, y1;
            if (side === 'left_side' || side === 'right_side') {
                let offset = mb[side];
                if (side === 'right_side') {
                    offset = this.fieldOfViewDims[0] - offset;
                }
                x0 = offset;
                y0 = 0;

                y1 = this.fieldOfViewDims[1];
                x1 = offset;
            } else {
                let offset = mb[side];
                if (side === 'bottom') {
                    offset = this.fieldOfViewDims[1] - offset;
                }
                x0 = 0;
                y0 = offset;

                x1 = this.fieldOfViewDims[0];
                y1 = offset;
            }

            return {
                type: 'rect',
                opacity: 1.0,
                line: {
                    color: 'rgb(255, 0, 0)',
                    dash: 'longdash'
                },
                x0,
                y0,
                x1,
                y1
            }
        });
    }

    removeCurrentlySelectedNonSegmentedPoint(selectedRoi) {
        if (this.selected_roi !== null &&
            this.selected_roi.contours === null &&
            this.selected_roi.label === 'not cell' &&
            this.selected_roi.id !== selectedRoi.id) {
            // If we had an ROI selected and it is not a cell,
            // and it is a nonsegmented point,
            // and it is not the current roi,
            // remove it
            this.rois = this.rois.filter(x => x.id !== this.selected_roi.id);
        }
    }

    async updateShapesOnProjection() {
        const contours = await this.getRoiContourShapes();
        const points = this.getRoiPointShapes();
        const regionBoundary = this.getRegionBoundariesShape();
        const motionBorder = await this.getMotionBorderShape();
        const shapes = [...contours, ...points, regionBoundary,
            ...motionBorder];
        Plotly.relayout('projection', {'shapes': shapes});
    }

    async #populateSubmittedRegionsTable() {
        const labels = await fetch('/get_user_submitted_labels')
            .then(res => res.json())
            .then(res => res['labels']);
        labels.forEach(l => {
            l.submitted = new Date(l.submitted).toLocaleString();
        });
        const tableRowsHtml = labels.map(l => {
            return `
                <tr>
                    <td>
                        ${l.submitted}
                    </td>
                    <td>
                        ${l.experiment_id}
                    </td>
                    <td>
                        ${l.region_id}
                    </td>
                </tr>
            `;
        }).join('');
        $('#regions-table-container').html(`
            <script>
                function datesSorter(a, b) {
                    return Date.parse(a) - Date.parse(b);
                }
            </script>
            <table id="submitted-regions-table" class="table table-sm table-hover" data-height="300" data-toggle="table">
                <thead>
                    <tr>
                        <th data-field="submitted" data-sortable="true" data-sorter="datesSorter">Submitted</th>
                        <th data-field="experiment_id">Exp. ID</th>
                        <th data-field="region_id" >Region ID</th>
                    </tr>
                </thead>
                <tbody>
                ${tableRowsHtml}
                </tbody>
            </table>`);
        $('#submitted-regions-table').bootstrapTable({
            onClickRow: (row, tr) => {
                this.#handleSubmittedRegionsTableCLick(row, tr);
            }
        });
    }

    async #handleSubmittedRegionsTableCLick(row, tr) {
        // Click the review tab
        $('#nav-review').tab('show');

        // Update button
        $('#submit_labels').text('Update labels for region');

        // highlight selected row
        $(tr).addClass('table-primary').siblings().removeClass('table-primary');

        const region_id = row['region_id'];

        const promises = [
            fetch(`http://localhost:${PORT}/get_labels_for_region?region_id=${region_id}`)
                .then(res => res.json())
                .then(res => res['labels']),
            this.loadNewRegion(region_id)
        ];

        const [labels, _] = await Promise.all(promises);

        const roiId_label_map = new Map();
        labels.forEach(label => {
            roiId_label_map.set(label['roi_id'], label['label']);
        })
        this.rois.forEach(roi => {
            roi.label = roiId_label_map.get(roi.id)
        });

        // add any non-segmented points
        labels.forEach(label => {
            if (label.point) {
                this.rois.push(new ROI({
                    id: label.roi_id,
                    experiment_id: this.experiment_id,
                    color: [255, 0, 0],
                    label: 'cell',
                    point: label.point
                }));
            }
        });
        this.updateShapesOnProjection();
    }

    #handleReviewNavClick() {
        const data = $('#submitted-regions-table').bootstrapTable('getData');
        const tr = $('#submitted-regions-table tbody').children('tr:first');
        this.#handleSubmittedRegionsTableCLick(data[0], tr);
    }
}

const getFieldOfViewDimensions = async function() {
        const field_of_view_dims = await fetch(
            `http://localhost:${PORT}/get_field_of_view_dimensions`
        )
            .then(data => data.json())
            .then(data => data['field_of_view_dimensions']);
        return field_of_view_dims;
    }

$(document).ready(async function () {
    const field_of_view_dims = await getFieldOfViewDimensions();
    const app = new CellLabelingApp({field_of_view_dims});
    app.loadNewRegion();
});