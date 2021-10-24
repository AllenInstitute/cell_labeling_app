const loadUsers = function() {
    $.get('/users/loadUsers').then(data => {
        const users = data['users'];
        const userSelectOptions = users.map(user => {
            return `<option value=${user}>${user}</option>`;
        });
        userSelectOptions.forEach(option => {
            $('select#inputEmail').append(option);
        });
    });
};

const login = function() {
    const email = $('#inputEmail').val();
    const postData = {
        email
    };
    return $.post('/users/login', JSON.stringify(postData)).then(() => {
        window.location = 'http://localhost:5000/';
    });
};

$( document ).ready(function() {
    loadUsers();
    
    $('button#login').on('click', () => {
        login();
    });

    $('button#register').on('click', () => {
        window.location = 'http://localhost:5000/users/register.html';
    });
});