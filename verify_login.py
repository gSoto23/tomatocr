
import requests

BASE_URL = "http://localhost:8000"

def verify_login():
    print("Attempting login...")
    # Using 'user' and 'pass' as field names to match HTML form
    data = {
        "user": "admin",
        "pass": "adminpassword" # Assuming default or known valid credentials
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/login", data=data, allow_redirects=False)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 303:
            print("Login Redirect Successful (303)")
            print(f"Location: {resp.headers.get('Location')}")
            print(f"Cookies: {resp.cookies.get_dict()}")
        elif resp.status_code == 200:
             print("Login Returned 200 (Maybe not redirecting? Or error page?)")
             print(resp.text[:500])
        else:
             print("Login Failed")
             print(resp.text)
             
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    verify_login()
