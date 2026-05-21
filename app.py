import os
import uuid
import base64
import requests
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# =========================
# LOAD ENVIRONMENT
# =========================
load_dotenv()

# =========================
# FLASK APP CONFIG
# =========================
app = Flask("X10THINK")

app.config['SECRET_KEY'] = os.getenv(
    'SECRET_KEY',
    'fallback_secret'
)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///x10think.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# =========================
# DATABASE
# =========================
db = SQLAlchemy(app)

# =========================
# DATABASE MODELS
# =========================
class User(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(200),
        nullable=False
    )

    points = db.Column(
        db.Integer,
        default=20
    )

    is_admin = db.Column(
        db.Boolean,
        default=False
    )

    images = db.relationship(
        'GeneratedImage',
        backref='owner',
        lazy=True
    )


class GeneratedImage(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    prompt = db.Column(
        db.Text,
        nullable=False
    )

    image_data = db.Column(
        db.Text,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),
        nullable=False
    )


class RechargeCode(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    code = db.Column(
        db.String(30),
        unique=True,
        nullable=False
    )

    point_value = db.Column(
        db.Integer,
        nullable=False
    )

    is_used = db.Column(
        db.Boolean,
        default=False
    )

# =========================
# HOME
# =========================
@app.route('/')
def home():

    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    return redirect(url_for('login'))

# =========================
# REGISTER
# =========================
@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        username = request.form.get('username')
        password = request.form.get('password')

        existing_user = User.query.filter_by(
            username=username
        ).first()

        if existing_user:

            flash(
                'Username already exists!',
                'danger'
            )

            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)

        new_user = User(
            username=username,
            password=hashed_password
        )

        db.session.add(new_user)
        db.session.commit()

        flash(
            'Account created successfully!',
            'success'
        )

        return redirect(url_for('login'))

    return render_template('register.html')

# =========================
# LOGIN
# =========================
@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(
            username=username
        ).first()

        if user and check_password_hash(
            user.password,
            password
        ):

            session['user_id'] = user.id
            session['is_admin'] = user.is_admin

            flash(
                'Login successful!',
                'success'
            )

            return redirect(url_for('dashboard'))

        flash(
            'Invalid credentials!',
            'danger'
        )

    return render_template('login.html')

# =========================
# DASHBOARD
# =========================
@app.route('/dashboard')
def dashboard():

    if 'user_id' not in session:

        return redirect(url_for('login'))

    user = db.session.get(
        User,
        session['user_id']
    )

    user_images = GeneratedImage.query.filter_by(
        user_id=user.id
    ).order_by(
        GeneratedImage.created_at.desc()
    ).all()

    return render_template(
        'dashboard.html',
        user=user,
        user_images=user_images
    )

# =========================
# IMAGE GENERATION
# =========================
@app.route('/generate', methods=['POST'])
def generate():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = db.session.get(
        User,
        session['user_id']
    )

    if user.points <= 0:

        flash(
            'Not enough points!',
            'danger'
        )

        return redirect(url_for('dashboard'))

    prompt = request.form.get('prompt')

    if not prompt:

        flash(
            'Prompt cannot be empty!',
            'warning'
        )

        return redirect(url_for('dashboard'))

    try:

        print("PROMPT:", prompt)

        image_url = f"https://image.pollinations.ai/prompt/{prompt}"

        response = requests.get(image_url)

        if response.status_code != 200:

            flash(
                'Image generation failed!',
                'danger'
            )

            return redirect(url_for('dashboard'))

        image_bytes = response.content

        encoded_image = base64.b64encode(
            image_bytes
        ).decode('utf-8')

        new_image = GeneratedImage(
            prompt=prompt,
            image_data=encoded_image,
            user_id=user.id
        )

        user.points -= 1

        db.session.add(new_image)

        db.session.commit()

        flash(
            'Image generated successfully!',
            'success'
        )

    except Exception as e:

        print("ERROR:", e)

        flash(
            f'Generation Error: {e}',
            'danger'
        )

    return redirect(url_for('dashboard'))

# =========================
# REDEEM RECHARGE CODE
# =========================
@app.route('/redeem', methods=['POST'])
def redeem():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = db.session.get(User, session['user_id'])
    input_code = request.form.get('code').strip()

    if not input_code:
        flash('Code cannot be empty!', 'warning')
        return redirect(url_for('dashboard'))

    db_code = RechargeCode.query.filter_by(code=input_code, is_used=False).first()

    if db_code:

        user.points += db_code.point_value
        db_code.is_used = True
        db.session.commit()
        flash(f'Successfully redeemed! {db_code.point_value} points added.', 'success')
    else:
        flash('Invalid or already used recharge code!', 'danger')

    return redirect(url_for('dashboard'))

# =========================
# DELETE IMAGE
# =========================
@app.route('/delete-image/<int:image_id>')
def delete_image(image_id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    image = GeneratedImage.query.get_or_404(image_id)

    if image.user_id != session['user_id']:

        flash(
            'Unauthorized access!',
            'danger'
        )

        return redirect(url_for('dashboard'))

    db.session.delete(image)
    db.session.commit()

    flash(
        'Image deleted successfully!',
        'success'
    )

    return redirect(url_for('dashboard'))

# =========================
# AI CHATBOT
# =========================
@app.route('/chat', methods=['POST'])
def chat():

    data = request.get_json()

    user_message = data.get('message').lower()

    if "hello" in user_message:
        reply = "Hello 👋 Welcome to X10THINK AI"

    elif "how are you" in user_message:
        reply = "I am doing great 🚀"

    elif "who made you" in user_message:
        reply = "I was created inside X10THINK 🔥"

    elif "python" in user_message:
        reply = "Python is powerful for AI & Web Development 🚀"

    elif "ai" in user_message:
        reply = "Artificial Intelligence is the future 🤖"

    else:
        reply = f"You said: {user_message}"

    return {
        "reply": reply
    }

# =========================
# ADMIN PANEL
# =========================
@app.route('/admin', methods=['GET', 'POST'])
def admin():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = db.session.get(
        User,
        session['user_id']
    )

    if not user.is_admin:

        flash(
            'Access Denied!',
            'danger'
        )

        return redirect(url_for('dashboard'))

    if request.method == 'POST':

        points = request.form.get('points')

        code = "X10-" + str(uuid.uuid4())[:8]

        new_code = RechargeCode(
            code=code,
            point_value=int(points)
        )

        db.session.add(new_code)

        db.session.commit()

        flash(
            'Recharge Code Created!',
            'success'
        )

    codes = RechargeCode.query.all()

    users = User.query.all()

    return render_template(
        'admin.html',
        codes=codes,
        users=users
    )

# =========================
# LOGOUT
# =========================
@app.route('/logout')
def logout():

    session.clear()

    flash(
        'Logged out successfully!',
        'info'
    )

    return redirect(url_for('login'))

# =========================
# RUN APP
# =========================
if __name__ == '__main__':

    with app.app_context():

        db.create_all()

        admin_exists = User.query.filter_by(
            username='admin'
        ).first()

        if not admin_exists:

            admin_user = User(
                username='admin',
                password=generate_password_hash('admin786'),
                is_admin=True,
                points=9999
            )

            db.session.add(admin_user)
            db.session.commit()

        print("DATABASE CREATED SUCCESSFULLY")

    app.run(debug=True)