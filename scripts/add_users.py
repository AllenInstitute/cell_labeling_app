import argschema
import json
import requests

class RegisterSchema(argschema.ArgSchema):
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
        emails = self.args['email_list']
        for email in emails:
            ans = requests.post(
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
                message = json.loads(ans.content)
                print(
                    f"Unexpected request error on {email}: "
                    f"Code: {ans.status_code}, message: {message['msg']}"
                )


if __name__ == "__main__":
    register = Register()
    register.run()
