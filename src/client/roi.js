class ROI {
    constructor({
                    id,
                    experiment_id,
                    color,
                    classifier_score=null,
                    label=null,
                    contours=null,
                    isUserAdded=false
    }={}) {
        /*
            id: ROI id. Null if user added.
            experiment_id: experiment id
            color: roi color
            classifier_score: pretrained classifier score. Null if user added.
            label: user label.
            contours: roi contours
            isUserAdded: whether the roi was algorithmically generated or
                user added
         */
        this.id = id;
        this.experiment_id = experiment_id;
        this.color = color;
        this.classifier_score = classifier_score;
        this.label = label;
        this.contours = contours;
        this.isUserAdded = isUserAdded;
    }
}

export {
    ROI
}