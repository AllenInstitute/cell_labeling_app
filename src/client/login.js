const loadUsers = function() {
    $.get('/users/loadUsers').then(data => {
        const users = data['users'];
        const userSelectOptions = users.map(user => {
            return `<option value=${user}>${user}</option>`;
        });
        userSelectOptions.forEach(option => {
            $('select#username').append(option);
        });
    });
};

const login = function() {
    const selectedUsername = $('select#username').children("option:selected").val();
    const postData = {
        user_id: selectedUsername
    };
    return $.post('/users/login', JSON.stringify(postData)).then(() => {
        window.location = 'http://localhost:5000/';
    });
};

$( document ).ready(function() {
    loadUsers();
    
    $('button#login').on('click', () => {
        login();
    })
});