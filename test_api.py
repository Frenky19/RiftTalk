import requests
import json

BASE_URL = "http://127.0.0.1:8000/api"

def test_api():
    print("🧪 Testing LoL Voice Chat API...")
    
    # Test health endpoint
    try:
        response = requests.get("http://127.0.0.1:8000/health")
        print(f"✅ Health check: {response.status_code}")
        print(f"📊 Health data: {response.json()}")
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return

    # Test authentication
    try:
        # Get JWT token
        auth_data = {
            "username": "test_summoner",
            "password": "test_password"  # In demo mode, any password works
        }
        
        response = requests.post(f"{BASE_URL}/auth/token", data=auth_data)
        if response.status_code == 200:
            token = response.json()["access_token"]
            print(f"✅ Authentication successful")
            print(f"🔑 Token: {token[:50]}...")
            
            headers = {"Authorization": f"Bearer {token}"}
            
            # Test voice room creation
            room_data = {
                "match_id": "test_match_123",
                "players": ["summoner1", "summoner2", "summoner3"]
            }
            
            response = requests.post(
                f"{BASE_URL}/voice/start", 
                json=room_data,
                headers=headers
            )
            
            if response.status_code == 200:
                room_info = response.json()
                print(f"✅ Voice room created: {room_info['room_id']}")
                print(f"👥 Players: {room_info['players']}")
            else:
                print(f"❌ Voice room creation failed: {response.status_code}")
                print(f"📋 Response: {response.text}")
                
        else:
            print(f"❌ Authentication failed: {response.status_code}")
            print(f"📋 Response: {response.text}")
            
    except Exception as e:
        print(f"❌ API test failed: {e}")

if __name__ == "__main__":
    test_api()
