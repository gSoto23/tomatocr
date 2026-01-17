
import requests

BASE_URL = "http://localhost:8000"

def verify_fix():
    print("1. Logging in...")
    s = requests.Session()
    # Assuming standard admin creds or the ones I used before
    resp = s.post(f"{BASE_URL}/login", data={"user": "admin", "pass": "adminpassword"}, allow_redirects=False)
    
    # Check if we got a cookie or token
    # The login endpoint sets a cookie 'access_token'
    if "access_token" not in s.cookies:
        print("Login failed (No cookie). Response:")
        print(resp.status_code)
        print(resp.text)
        # Try to login with different creds? 
        # Actually I can't guess them easily. 
        # I'll try to rely on the fact that if I hit the endpoint and get past authentication, I'm good.
        # But verify_password might fail.
        # I'll try to Create a user if I can? No, need auth to create.
        return

    print("Login successful (Cookie set).")
    
    # 2. Update User 1 (Admin) - harmless update
    print("2. Updating User 1...")
    data = {
        "username": "admin",
        "full_name": "Admin User",
        "role": "admin",
        "is_active": True,
        "payment_method": "Efectivo",
        "apply_deductions": True 
    }
    
    # We need to provide all required fields or they default?
    # update_user has many Form(...) fields.
    # required: username, full_name, role.
    
    resp = s.post(f"{BASE_URL}/users/1/edit", data=data, allow_redirects=False)
    print(f"Update Status: {resp.status_code}")
    
    if resp.status_code == 500:
        print("FAILURE: Still 500 Error.")
        print(resp.text)
    elif resp.status_code == 303:
        print("SUCCESS: Redirected (303). Update likely successful.")
    else:
        print(f"Unexpected status: {resp.status_code}")
        print(resp.text)

if __name__ == "__main__":
    verify_fix()
