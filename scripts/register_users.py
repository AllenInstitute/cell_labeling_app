import argschema
import json
import requests


class RegisterSchema(argschema.ArgSchema):
    admin_username = argschema.fields.String(
        required=True,
        description='Admin username, in order to authenticate against the '
                    '/users/register api'
    )
    email_list = argschema.fields.List(
        argschema.fields.String,
        required=True,
        cli_as_single_argument=True,
        description='List of emails to register in the app.'
    )
    port = argschema.fields.Int(
        default=5000,
        description='Port the app is running on on the localhost.'
    )


class Register(argschema.ArgSchemaParser):
    """Add a list of users to the app"""
    default_schema = RegisterSchema

    def run(self):
        session = self._establish_session()
        emails = self.args['email_list']
        for email in emails:
            ans = session.post(
                url=f"http://localhost:{self.args['port']}/users/register",
                data=json.dumps({"email": email})
            )
            if ans.status_code == 400:
                message = json.loads(ans.content)
                print(
                    f"Did not add {email}. Code 400 failure with message: "
                    f"{message['msg']}"
                )
            elif ans.status_code == 200:
                print(f"Successfully added {email}")
            else:
                print(
                    f"Unexpected request error on {email}: "
                    f"Code: {ans.status_code}, message: {ans.content}"
                )

    def _establish_session(self) -> requests.Session:
        """Logs admin_username in in order to establish a session"""
        session = requests.Session()
        res = session.post(
            url=f'http://localhost:{self.args["port"]}/users/login',
            data=json.dumps({'email': self.args['admin_username']})
        )
        if res.status_code != 200:
            print(f'Unable to login {self.args["admin_username"]}')
        return session


if __name__ == "__main__":
    register = Register()
    register.run()
