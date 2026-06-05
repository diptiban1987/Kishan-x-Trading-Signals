from app import app, get_user_plan

with app.app_context():
    print("User 3 plan:", get_user_plan(3))
