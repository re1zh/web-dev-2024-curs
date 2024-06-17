from flask_login import current_user

class UsersPolicy:
    def __init__(self, user):
        self.user = user

    def view_profile(self):
        return True

    def update_profile_employer(self):
        return current_user.is_employer() or current_user.is_admin()

    def update_profile_job_seeker(self):
        return current_user.is_job_seeker() or current_user.is_admin()

    def create_vacancie(self):
        return current_user.is_employer() or current_user.is_admin()

    def create_resume(self):
        return current_user.is_job_seeker() or current_user.is_admin()

    def create_request(self):
        return current_user.is_job_seeker() or current_user.is_admin()

    def update_vacancie(self):
        return current_user.is_employer() or current_user.is_admin()

    def update_resume(self):
        return current_user.is_job_seeker() or current_user.is_admin()

    def update_request(self):
        return current_user.is_employer() or current_user.is_admin()

    def delete_vacancie(self):
        return current_user.is_employer() or current_user.is_admin()

    def delete_resume(self):
        return current_user.is_job_seeker() or current_user.is_admin()

    def delete_request(self):
        return current_user.is_job_seeker() or current_user.is_admin()

    def is_admin(self):
        return current_user.is_admin()