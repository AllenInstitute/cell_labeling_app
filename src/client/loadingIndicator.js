class LoadingIndicator {
    /* Displays status of loading elements on the page */
    
    constructor() {
        this.loadingTxt = [];
    }

    add(msg) {
        this.loadingTxt.push(msg);
        $('#loading_text').text(this.loadingTxt[this.loadingTxt.length-1]);
    }

    remove(msg) {
        this.loadingTxt = this.loadingTxt.filter(txt => txt != msg);
        if (this.loadingTxt.length > 0) {
            $('#loading_text').text(this.loadingTxt[this.loadingTxt.length-1]);
        } else {
            $('#loading_text').text('');
        }
    }
}

export {
    LoadingIndicator
}