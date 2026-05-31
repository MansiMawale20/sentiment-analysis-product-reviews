from flask import *

from flask_sqlalchemy import SQLAlchemy

from flask_bcrypt import Bcrypt

from transformers import pipeline

from scraper.amazon_api import scrape_amazon

import random

# ============================================
# FLASK SETUP
# ============================================

app = Flask(__name__)

app.secret_key = "secret123"

app.config[
    'SQLALCHEMY_DATABASE_URI'
] = 'mysql+pymysql://root:admin123@localhost/universal_review_analyzer'
app.config[
    'SQLALCHEMY_TRACK_MODIFICATIONS'
] = False

db = SQLAlchemy(app)

bcrypt = Bcrypt(app)

# ============================================
# AI SENTIMENT MODEL
# ============================================

classifier = pipeline(
    "sentiment-analysis"
)

# ============================================
# DATABASE MODELS
# ============================================

class User(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    username = db.Column(
        db.String(100),
        unique=True
    )

    email = db.Column(
        db.String(100),
        unique=True
    )

    password = db.Column(
        db.String(200)
    )


class AnalysisHistory(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer
    )

    product_name = db.Column(
        db.String(500)
    )

    product_rating = db.Column(
        db.String(20)
    )

    pos_count = db.Column(
        db.Integer
    )

    neg_count = db.Column(
        db.Integer
    )

    neutral_count = db.Column(
        db.Integer
    )

    fake_review_count = db.Column(
        db.Integer
    )

    real_review_count = db.Column(
        db.Integer
    )

    total_reviews = db.Column(
        db.Integer
    )

# ============================================
# CREATE DATABASE
# ============================================

with app.app_context():

    db.create_all()

# ============================================
# LOGIN CHECK
# ============================================

def login_required():

    return 'user_id' in session

# ============================================
# HOME
# ============================================

@app.route('/')
def home():

    return render_template(
        'index.html'
    )
# ============================================
# REGISTER
# ============================================

@app.route(
    '/register',
    methods=['GET', 'POST']
)
def register():

    if request.method == 'POST':

        username = request.form[
            'username'
        ]

        email = request.form[
            'email'
        ]

        password = request.form[
            'password'
        ]

        hashed_password = bcrypt.generate_password_hash(
            password
        ).decode('utf-8')

        new_user = User(

            username=username,

            email=email,

            password=hashed_password
        )

        db.session.add(
            new_user
        )

        db.session.commit()

        return redirect(
            url_for('login')
        )

    return render_template(
        'register.html'
    )

# ============================================
# LOGIN
# ============================================

@app.route(
    '/login',
    methods=['GET', 'POST']
)
def login():

    if request.method == 'POST':

        email = request.form[
            'email'
        ]

        password = request.form[
            'password'
        ]

        user = User.query.filter_by(
            email=email
        ).first()

        if user and bcrypt.check_password_hash(
            user.password,
            password
        ):

            session['user_id'] = user.id

            return redirect(
                url_for('product')
            )

    return render_template(
        'login.html'
    )

# ============================================
# LOGOUT
# ============================================

@app.route('/logout')
def logout():

    session.clear()

    return redirect(
        url_for('login')
    )

# ============================================
# PRODUCT PAGE
# ============================================

@app.route('/product')
def product():

    if not login_required():

        return redirect(
            url_for('login')
        )

    return render_template(
        'product.html'
    )

# ============================================
# ANALYZE AMAZON PRODUCT
# ============================================

@app.route(
    '/analyze_amazon',
    methods=['POST']
)
def analyze_amazon():

    try:

        data = request.get_json()

        url = data.get('url')

        (
            product_name,
            product_image,
            product_rating,
            reviews
        ) = scrape_amazon(url)

        analyzed_reviews = []

        positive = 0

        negative = 0

        neutral = 0

        fake_count = 0

        real_count = 0

        # ====================================
        # ANALYZE REVIEWS
        # ====================================

        for review in reviews:

            result = classifier(review)[0]

            label = result['label']

            score = result['score']

            # ====================================
            # SENTIMENT
            # ====================================

            if label == 'POSITIVE':

                sentiment = "Positive"

                positive += 1

            else:

                sentiment = "Negative"

                negative += 1

            # ====================================
            # SIMPLE NEUTRAL DETECTION
            # ====================================

            if score < 0.65:

                sentiment = "Neutral"

                neutral += 1

                if label == 'POSITIVE':

                    positive -= 1

                else:

                    negative -= 1

            # ====================================
            # FAKE REVIEW DETECTION
            # ====================================

            fake_words = [

                "best",
                "amazing",
                "100%",
                "must buy",
                "awesome"
            ]

            fake_review = "Real Review"

            for word in fake_words:

                if word.lower() in review.lower():

                    fake_review = "Fake Review"

                    fake_count += 1

                    break

            if fake_review == "Real Review":

                real_count += 1

            analyzed_reviews.append({

                "review": review,

                "sentiment": sentiment,

                "fake_review": fake_review
            })

        # ====================================
        # RECOMMENDATION
        # ====================================

        recommendation = "Recommended"

        if negative > positive:

            recommendation = (
                "Not Recommended"
            )

        # ====================================
        # SAVE HISTORY
        # ====================================

        history = AnalysisHistory(

            user_id=session['user_id'],

            product_name=product_name,

            product_rating=product_rating,

            pos_count=positive,

            neg_count=negative,

            neutral_count=neutral,

            fake_review_count=fake_count,

            real_review_count=real_count,

            total_reviews=len(reviews)
        )

        db.session.add(history)

        db.session.commit()

        # ====================================
        # FINAL RESPONSE
        # ====================================

        return jsonify({

            "product_name":
            product_name,

            "product_image":
            product_image,

            "product_rating":
            product_rating,

            "positive":
            positive,

            "negative":
            negative,

            "neutral":
            neutral,

            "recommendation":
            recommendation,

            "reviews":
            analyzed_reviews
        })

    except Exception as e:

        print(
            "APP ERROR:",
            e
        )

        return jsonify({

            "error":
            str(e)
        })

# ============================================
# HISTORY PAGE
# ============================================

@app.route('/history')
def history():

    if not login_required():

        return redirect(
            url_for('login')
        )

    all_products = AnalysisHistory.query.filter_by(
        user_id=session['user_id']
    ).all()

    return render_template(

        'history.html',

        all_products=all_products
    )

# ============================================
# DASHBOARD
# ============================================

@app.route('/dashboard')
def dashboard():

    if not login_required():

        return redirect(
            url_for('login')
        )

    all_products = AnalysisHistory.query.filter_by(
        user_id=session['user_id']
    ).all()

    total_products = len(all_products)

    total_positive = 0

    total_negative = 0

    total_neutral = 0

    total_fake = 0

    total_real = 0

    total_reviews = 0

    for item in all_products:

        total_positive += item.pos_count

        total_negative += item.neg_count

        total_neutral += item.neutral_count

        total_fake += item.fake_review_count

        total_real += item.real_review_count

        total_reviews += item.total_reviews

    return render_template(

        'dashboard.html',

        all_products=all_products,

        total_products=total_products,

        total_positive=total_positive,

        total_negative=total_negative,

        total_neutral=total_neutral,

        total_fake=total_fake,

        total_real=total_real,

        total_reviews=total_reviews
    )

# ============================================
# RUN APP
# ============================================

if __name__ == '__main__':

    app.run(
        debug=True
    )