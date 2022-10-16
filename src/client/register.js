const displayErrorMsg = function(msg) {
    $('#emailInvalid').text(msg);
    $('#inputEmail').addClass('is-invalid');
}

const register = function() {
    const email = $('#inputEmail').val();

    if (!email) {
        displayErrorMsg('Email address cannot be blank');
        return;
    }

    const postData = {
        email
    };
    $.post('/users/register', JSON.stringify(postData))
        .then(() => {
            window.location = `http://${SERVER_ADDRESS}:${PORT}/`;
        })
        .catch(error => {
            displayErrorMsg(error.responseJSON['msg']);
        });
};

$( document ).ready(function() {    
    $('button#register').on('click', () => {
        register();
    });
});