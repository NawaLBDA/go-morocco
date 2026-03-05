from locust import HttpUser, task, between

class WebsiteUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def index(self):
        self.client.get("/")

    @task(3)
    def search(self):
        self.client.get("/?q=morocco")

    @task(2)
    def contact(self):
        self.client.get("/contact/")

    @task(1)
    def register(self):
        self.client.get("/register/")
