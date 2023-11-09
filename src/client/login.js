const login = function() {
    const email = $('#inputEmail').val();
    const postData = {
        email
    };
    return $.post('/users/login', JSON.stringify(postData))
    .then(() => {
        window.location = `http://${SERVER_ADDRESS}/`;
    }).catch(() => alert('The login did not work'));
};

$( document ).ready(function() {
    $('button#login').on('click', () => {
        login();
    });

    $('button#register').on('click', () => {
        window.location = `http://${SERVER_ADDRESS}/users/register.html`;
    });
});