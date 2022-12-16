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

        $('button#update_labels').on('click', () => {
            this.handleSubmitRegion({isUpdate: true});
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

        $('#nav-review-tab').on('click', () => {
            this.#handleReviewNavClick();
        });

        $('#nav-label-tab').on('click', () => {
            this.#handleLabelNewRegionClick();
        });

        $('#in-progress-no, #in-progress-modal-close').on('click', () => {
            $('#in-progress-warning-modal').modal('hide');
        });
    }

    addProjectionListeners() {
        const projection = document.getElementById('projection');

        projection.on('plotly_click', data => {
            const point = data.points[0];
            const [y, x] = point.pointIndex;
            this.handleProjectionClick(x, y);
        });

        projection.on('plotly_selected', () => {
           this.handleDrawSegmentationOutline();
        });

        projection.on('plotly_relayout', () => {
            this.handleProjectionRelayout();
        });

    }

    displayTrace() {
        return fetch(`http://${SERVER_ADDRESS}/get_trace`,
        {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                experiment_id: this.experiment_id,
                roi: this.selected_roi
            })
        }).then(async response => await response.json())
        .then(data => {
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
            // Add all user-added rois
            this.rois.filter(x => x.isUserAdded)
                .forEach(roi => rois.push(roi));
        }

        if (rois === null) {
            $("#projection_include_mask_outline").attr("disabled", true);
            const url = `http://${SERVER_ADDRESS}/get_roi_contours?experiment_id=${this.experiment_id}&current_region_id=${this.region['id']}`;
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
                this.roisUnchanged = JSON.parse(JSON.stringify(rois));

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
                },
                editable: rois[i].isUserAdded,
                roiId: rois[i].id
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
        const url = `http://${SERVER_ADDRESS}/get_projection?type=${projection_type}&experiment_id=${this.experiment_id}`;
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
                    },
                    // Segmentation outlines manually drawn on projection
                    newshape: {
                        line: {
                            color: 'rgb(255, 0, 0)'
                        }
                    }
                };

                const config = {
                    doubleClick: false,
                    modeBarButtonsToAdd: ['drawclosedpath', 'eraseshape']
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
            videoTimeframe = await fetch(`http://${SERVER_ADDRESS}/get_default_video_timeframe`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        experiment_id: this.experiment_id,
                        roi: this.selected_roi
                    })
                }).then(async response => await response.json())
                .then(data => data['timeframe']);
        }

        videoTimeframe = [parseInt(videoTimeframe[0]), parseInt(videoTimeframe[1])]

        const url = `http://${SERVER_ADDRESS}/get_video`;
        const postData = {
            experiment_id: this.experiment_id,
            roi_id: this.selected_roi.id,
            color: this.selected_roi.color,
            region_id: this.region['id'],
            fovBounds: this.fovBounds,
            include_current_roi_mask: this.show_current_roi_outline_on_movie,
            include_all_roi_masks: this.show_all_roi_outlines_on_movie,
            timeframe: videoTimeframe,
            is_user_added: this.selected_roi.isUserAdded,
            contours: this.selected_roi.contours
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

    initialize() {
        this.show_current_region_roi_contours_on_projection = $('#projection_include_mask_outline').is(':checked');
        this.show_current_roi_outline_on_movie = $('#video_include_mask_outline').is(':checked');
        this.show_all_roi_outlines_on_movie = $('#video_include_surrounding_rois').is(':checked');
        this.is_trace_shown = false;
        this.is_video_shown = false;
        this.rois = null;
        this.roisUnchanged = null;
        this.discrepancy_rois = null;
        this.fovBounds = null;
        this.experiment_id = null;
        this.projection_is_shown = false;
        this.projection_raw = null;
        this.region = null;
        this.is_loading_new_region = false;
        this.selected_roi = null;
        this.notes = new Map();
        this.notesUnchanged = new Map();
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
        /* Loads a new region

        Args
        ------
        - region_id:
            Load a specific region.
        */
        if (!region_id) {
            // If region id is not passed, we should be submitting,
            // rather than updating
            $('#submit_labels').show();
        }
        $('#projection-spinner').show();
        $('#movie').remove();
        this.initialize();
        $('#loading_text').css('display', 'inline');

        let region;
        try {
            if (region_id === null) {
                // Loading a random region
                this.#populateSubmittedRegionsTable();
                this.#updateProgress();
                region = await $.get(`http://${SERVER_ADDRESS}/get_random_region`, data => {
                    if (data['region'] === null) {
                        // No more regions to label
                        window.location = `http://${SERVER_ADDRESS}/done.html`;
                    }
                });
            } else {
                // Loading a specific region
                region = await fetch(`http://${SERVER_ADDRESS}/get_region?region_id=${region_id}`)
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
            $.post(`http://${SERVER_ADDRESS}/get_fov_bounds`, JSON.stringify(region['region'])),
            fetch(`http://${SERVER_ADDRESS}/get_motion_border?experiment_id=${this.experiment_id}`
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

    submitRegion({isUpdate = false}={}) {
        /* Submit labels for region *

        Args
        ----------
        - isUpdate:
            Whether updating labels
        /
         */
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
                    .map(x => {
                        return {
                            roi_id: x.id,
                            is_user_added: x.isUserAdded,
                            contours: x.isUserAdded ? x.contours : null,
                            label: x.label
                        }
                    }),
            roi_extra,
            duration: (Date.now() - this.labelingStart) / 1000
        };

        let url;
        if (isUpdate) {
            url = `http://${SERVER_ADDRESS}/update_labels_for_region`;
        } else {
            url = `http://${SERVER_ADDRESS}/submit_region`;
        }

        return $.post(url, JSON.stringify(data))
            .then(async () => {
                let msg;
                if (isUpdate) {
                    msg = `Successfully updated labels for region ${this.region['id']}`;
                } else {
                    msg = 'Successfully submitted labels for region<br>Loading next region';
                }
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

    handleDrawSegmentationOutline() {
        const shapes = document.getElementById('projection').layout.shapes;

        // Get user-added shape
        const userAddedshapeIndex = shapes.findLastIndex(x => x.editable);

        const userAddedShape = shapes[userAddedshapeIndex];

        const contours = this.#getContoursFromSVGPath(userAddedShape.path);

        // Assigning a new roi id that is greater than max
        const roiId = Math.max(...this.rois.map(x => x.id)) + 100;

        this.rois.push(new ROI({
            id: roiId,
            experiment_id: this.experiment_id,
            color: [255, 0, 0],
            classifier_score: null,
            label: 'cell',
            contours,
            isUserAdded: true
        }));

        // Setting dragmode to false so that the drawing tool is deselected
        // After drawing
        Plotly.relayout(
            'projection',
            {'dragmode': false}
        );

        this.#handleSegmentedPointClick({roi_id: roiId});
    }

    handleProjectionRelayout(projectionShapes) {
        const shapes = document.getElementById('projection').layout.shapes;
        const userAddedROIs = this.rois.filter(roi => roi.isUserAdded);
        const userAddedShapes = shapes.filter(x => x.editable);

        if(userAddedROIs.length > userAddedShapes.length) {
            // The user deleted an ROI
            this.handleDeleteROI();
        } else {
            // The user might have modified an ROI
            this.handleMaybeROIModified();
        }
    }

    handleDeleteROI() {
        /*
        Checks which ROI shape was deleted and deletes it from the set of rois
         */
        const shapes = document.getElementById('projection').layout.shapes;
        const userAddedShapes = shapes.filter(x => x.editable);
        const userAddedROIs = this.rois.filter(roi => roi.isUserAdded);

        const userAddedShapeRoiIds = new Set(userAddedShapes.map(x => x.roiId));

        const deletedRoiId = userAddedROIs.find(
            x => !userAddedShapeRoiIds.has(x.id));
        this.rois = this.rois.filter(x => x.id !== deletedRoiId.id);

    }

    handleMaybeROIModified() {
        /*
        Updates contours of roi in case the currently selected roi
        had its vertices updated
         */
        if (this.selected_roi !== null) {
            const maybeModifiedShape =
                document.getElementById('projection').layout.shapes
                .find(x => x.hasOwnProperty('roiId') &&
                    x.roiId === this.selected_roi.id);
            if (maybeModifiedShape !== undefined) {
                const roiIdx = this.rois.findIndex(
                    x => x.id === this.selected_roi.id);
                this.rois[roiIdx].contours = this.#getContoursFromSVGPath(
                    maybeModifiedShape.path)
            }
        }

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
            user_added_rois: this.rois.filter(x => x.isUserAdded),
            coordinates: [x, y]
        }
        postData = JSON.stringify(postData);


        const res = await fetch(`http://${SERVER_ADDRESS}/find_roi_at_coordinates`,
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
            // Do nothing. Clicking outside an ROI.
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

        if (this.selected_roi !== null &&
            this.selected_roi.id === selectedRoi.id &&
            // don't toggle label on user added ROI
            !this.selected_roi.isUserAdded
        ) {
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

    #updateSideNav() {
        /* Updates the sidenav because a new point has been clicked */
        const roi_id = this.selected_roi.id;
        const roiText = `ROI ${roi_id}`;
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

        if (this.selected_roi.isUserAdded) {
            $('#roi-sidenav #roi-classifier-score').text('');
        } else {
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

    handleSubmitRegion({userHasReviewed = false, isUpdate = false} = {}) {
        /* Handles submit labels button click 
        
        Args
        ------
        - userHasReviewed:
            Whether the user has reviewed any label-classifier 
            discrepancies and chose to ignore them
        - isUpdate:
            Whether updating existing labels
        */
        $('button#submit_labels').attr('disabled', true);

        if (!userHasReviewed) {
            const isValid = this.validateLabels({isUpdate});
            if (!isValid) {
                $('button#submit_labels').attr('disabled', false);
                return;
            }
        }

        this.submitRegion({isUpdate}).then(() => {
            if (!isUpdate) {
                this.loadNewRegion();
            } else {
                // Set the unchanged state to the currently submitted state
                this.roisUnchanged = JSON.parse(JSON.stringify(this.rois));
                this.notesUnchanged = new Map(this.notes);
            }
        }).catch(e => {
            $('button#submit_labels').attr('disabled', false);
        });
    }

    validateLabels({isUpdate = false}={}) {
        /* Flags any rois which might have been incorrectly labeled.
        Any rois with a label that disagrees with the classifier score are flagged */
        const maybeCell = this.rois
            .filter(x => {
                return x.classifier_score !== null &&
                    x.classifier_score >= 0.5 &&
                    x.label !== 'cell'
            });
        const maybeNotCell = this.rois
            .filter(x => {
                return x.classifier_score !== null &&
                    x.classifier_score < 0.5 &&
                    x.label === 'cell'
            });

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
                this.handleSubmitRegion({userHasReviewed: true, isUpdate});
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

    async updateShapesOnProjection() {
        const contours = await this.getRoiContourShapes();
        const regionBoundary = this.getRegionBoundariesShape();
        const motionBorder = await this.getMotionBorderShape();
        const shapes = [...contours, regionBoundary,
            ...motionBorder];
        Plotly.relayout('projection', {'shapes': shapes});

        // Add listener for clicking the stroke (exterior) of editable shapes,
        // Since plotly_click event is not triggered in that case
        shapes
            .map((x, idx) => x.editable ? idx : -1)
            .filter(idx => idx > 0)
            .forEach(idx => {
                d3.select(`.shapelayer path:nth-child(${idx+1})`)
                .attr('pointer-events', 'stroke')
                .on('click', () => {
                    this.handleUserDrawnSegmentationOutlineClick(idx);
                });
            });
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
                        <th data-field="experiment_id" data-sortable="true">Exp. ID</th>
                        <th data-field="region_id">Region ID</th>
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

        // Toggle review tab state
        if (labels.length === 0) {
            $('#nav-review-tab').addClass('disabled');
        } else {
            $('#nav-review-tab').removeClass('disabled');
        }
    }

    async #handleSubmittedRegionsTableCLick(row, tr) {
        /*
        At this point, shapes are already drawn onto projection
        and all ROIs already loaded into memory.
        This updates labels and adds any user added ROIs

        - row: row metadata
        - tr: row dom node
         */
        const handleReviewTableClickOk = async () => {
            // hide submit labels button and show update button
            $('#submit_labels').hide();
            $('#update_labels').show();

            // Click the review tab
            $('#nav-review-tab').tab('show');

            // highlight selected row
            $(tr).addClass('table-primary').siblings().removeClass('table-primary');

            const region_id = row['region_id'];

            const promises = [
                fetch(`http://${SERVER_ADDRESS}/get_labels_for_region?region_id=${region_id}`)
                    .then(res => res.json()),
                this.loadNewRegion(region_id)
            ];

            let [labels, _] = await Promise.all(promises);

            const roiExtra = labels['roi_extra'];
            labels = labels['labels'];

            // Update notes
            roiExtra.forEach(v => {
                this.notes.set(v.roi_id, v.notes);
            });
            this.notesUnchanged = new Map(this.notes);

            // Update labels
            const roiId_label_map = new Map();
            labels.forEach(label => {
                roiId_label_map.set(label['roi_id'], label['label']);
            })
            this.rois.forEach(roi => {
                roi.label = roiId_label_map.get(roi.id)
            });

            // add any user-added ROIs
            labels.forEach(label => {
                if (label.is_user_added) {
                    this.rois.push(new ROI({
                        id: label.roi_id,
                        experiment_id: this.experiment_id,
                        color: [255, 0, 0],
                        label: 'cell',
                        isUserAdded: label.is_user_added,
                        contours: label.contours
                    }));
                }
            });
            this.roisUnchanged = JSON.parse(JSON.stringify(this.rois));
            this.updateShapesOnProjection();
        }
        const isUnsavedChanges = this.#isUnsavedChanges();
        if (isUnsavedChanges) {
            this.#handleUnsavedChanges(handleReviewTableClickOk);
            return;
        }

        handleReviewTableClickOk();
    }

    #handleReviewNavClick() {
        const handleReviewNavClickOk = () => {
            const data = $('#submitted-regions-table').bootstrapTable('getData');
            const tr = $('#submitted-regions-table tbody').children('tr:first');
            this.#handleSubmittedRegionsTableCLick(data[0], tr);
        };
        const isUnsavedChanges = this.#isUnsavedChanges();
        if (isUnsavedChanges) {
            this.#handleUnsavedChanges(handleReviewNavClickOk);
            return;
        }
        handleReviewNavClickOk();
    }

    #handleUnsavedChanges(callable) {
        $('#in-progress-warning-modal').modal('show');

        $('#in-progress-ok').off('click');
        $('#in-progress-ok').on('click', () => {
            $('#in-progress-warning-modal').modal('hide');
            callable();
        });
    }

    #handleLabelNewRegionClick() {
        const handleLabelNewRegionClickOk = () => {
            // hide update labels button and show submit button
            $('#submit_labels').show();
            $('#update_labels').hide();

            $('#nav-label-tab').tab('show');
            $('#submitted-regions-table tbody tr').each(_, v => {
                v.removeClass('table-primary');
            });
            this.loadNewRegion();
        }

        const isUnsavedChanges = this.#isUnsavedChanges();
        if (isUnsavedChanges) {
            this.#handleUnsavedChanges(handleLabelNewRegionClickOk);
            return;
        }
        handleLabelNewRegionClickOk();
    }

    async #updateProgress() {
        fetch(
        `http://${SERVER_ADDRESS}/get_label_stats`
        )
        .then(data => data.json())
        .then(stats => {
            const total = stats['n_total'];
            const completed = stats['n_completed'];
            const completedByOthers = stats['n_completed_by_others'];
            const userLabeled = stats['n_user_has_labeled'];
            const numLabelersRequiredPerRegion = stats['num_labelers_required_per_region'];
            const totalProgress = completed / total;
            const userProgress = userLabeled / (total - completedByOthers);

            const progressHtml = `
                <p>${userLabeled} / ${total - completedByOthers} labeled</p>
                <div class="progress">
                    <div class="progress-bar" role="progressbar" style="width: ${userProgress * 100}%;" aria-valuenow="${userLabeled}" aria-valuemin="0" aria-valuemax="${total}"></div>
                </div>
                <p style="margin-top: 10px">${completed} / ${total} labeled by ${numLabelersRequiredPerRegion} labelers</p>
                <div class="progress">
                    <div class="progress-bar" role="progressbar" style="width: ${totalProgress * 100}%;" aria-valuenow="${completed}" aria-valuemin="0" aria-valuemax="${total}"></div>
                </div>`;

            $('#progress-container').html(progressHtml);
            }
        );
    }

    #isUnsavedChanges() {
        /* Check if the user made any unsaved changes */
        const rois = this.rois
            // Filtering out any currently selected non-cell points
            .filter(x => x.contours !== null ||
                   (x.point !== null && x.label === 'cell'));

        if (rois.length !== this.roisUnchanged.length) {
            return true;
        }

        return rois.some((roi, idx) => {
            if (roi.label !== this.roisUnchanged[idx].label) {
                return true;
            }

            if (this.notes.get(roi.id) !== this.notesUnchanged.get(roi.id)) {
                return true;
            }
            return false;
        });
    }

    #getContoursFromSVGPath(path) {
        /*
            path: svg path string
         */
        // Remove the first character "M" and the last character "Z"
        path = path.substring(1, path.length - 1);

        path = path.split('L');
        path = path.map(coords => coords.split(','));
        const contours = path.map(coords => {
            let [x, y] = coords;
            x = parseInt(x);
            y = parseInt(y);
            return [x, y];
        });
        return [contours];
    }

    handleUserDrawnSegmentationOutlineClick(idx) {
        /*
        Finds the ROI belonging to the clicked shape at `idx`
         */
        const domShapes = document.getElementById('projection').layout.shapes;
        const clickedRoi = this.rois.find(x => x.id === domShapes[idx].roiId);
        this.#handleSegmentedPointClick({roi_id: clickedRoi.id});
    }
}

const getFieldOfViewDimensions = async function() {
        const field_of_view_dims = await fetch(
            `http://${SERVER_ADDRESS}/get_field_of_view_dimensions`
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