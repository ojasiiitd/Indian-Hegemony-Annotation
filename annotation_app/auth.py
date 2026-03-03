from flask import Blueprint, render_template, request, redirect, url_for, session, abort
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
import json
import os
from config import KEYS, REGION_STATE_MAP

auth_bp = Blueprint("auth", __name__)

ANNOTATORS_FILE = "annotators.json"


# =========================
# Utility
# =========================

def load_annotators():
    if not os.path.exists(ANNOTATORS_FILE):
        return []
    with open(ANNOTATORS_FILE, "r") as f:
        return json.load(f)


def save_annotators(data):
    with open(ANNOTATORS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_region_from_state(state):
    for region, states in REGION_STATE_MAP.items():
        if state in states:
            return region
    return None


# =========================
# ACCESS CODE PAGE
# =========================

@auth_bp.route("/access-code", methods=["GET", "POST"])
def access_code():
    if request.method == "POST":
        secret_code = request.form["secret_code"]

        if check_password_hash(KEYS["ANNOTATOR_PASSWORD_HASH"], secret_code):
            session["signup_allowed"] = True
            return redirect(url_for("auth.signup"))

        return render_template("access_code.html", error="Invalid access code")

    return render_template("access_code.html")


# =========================
# SIGNUP (PROTECTED)
# =========================

@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():

    # 🚫 Prevent direct access
    if not session.get("signup_allowed"):
        return redirect(url_for("auth.access_code"))

    if request.method == "POST":

        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        state = request.form["state"]
        region = get_region_from_state(state)

        annotators = load_annotators()

        if any(u["username"] == username for u in annotators):
            return render_template("signup.html",
                                   region_state_map=REGION_STATE_MAP,
                                   error="Username already exists")

        new_user = {
            "username": username,
            "password": password,
            "state": state,
            "region": region,
            "age_group": request.form["age_group"],
            "gender": request.form["gender"],
            "education_level": request.form["education_level"],
            "field_of_study": request.form["field_of_study"],
            "social_theory_training": request.form["social_theory_training"],
            "llm_experience_level": request.form["llm_experience_level"],
            "urban_rural_background": request.form["urban_rural_background"],
            "created_at": datetime.utcnow().isoformat()
        }

        annotators.append(new_user)
        save_annotators(annotators)

        # Remove access flag
        session.pop("signup_allowed", None)

        # Auto login
        session["user"] = {
            "username": username,
            "role": "annotator",
            "state": state,
            "region": region
        }

        return redirect(url_for("annotate"))

    return render_template("signup.html",
                           region_state_map=REGION_STATE_MAP)


# =========================
# LOGIN
# =========================

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # ---- ADMIN LOGIN ----
        if (
            username == KEYS["ADMIN_USERNAME"] and
            check_password_hash(KEYS["ADMIN_PASSWORD_HASH"], password)
        ):
            session["user"] = {
                "username": username,
                "role": "admin"
            }
            return redirect(url_for("annotate"))

        # ---- ANNOTATOR LOGIN ----
        annotators = load_annotators()
        for user in annotators:
            if user["username"] == username and check_password_hash(user["password"], password):
                session["user"] = {
                    "username": username,
                    "role": "annotator",
                    "state": user["state"],
                    "region": user["region"]
                }
                return redirect(url_for("annotate"))

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


# =========================
# LOGOUT
# =========================

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))