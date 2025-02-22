from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore, auth
import random
import numpy as np
from sklearn.cluster import KMeans

# Initialize Firebase
cred = credentials.Certificate("C:/Users/maria/Documents/umsports-linksync-firebase-adminsdk-fbsvc-11d77d7d69.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

app = Flask(__name__)

# --------------------------- USER LOGIN ---------------------------
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    # Query Firestore for user
    user_ref = db.collection('users').where('username', '==', username).stream()
    user_data = next((doc.to_dict() for doc in user_ref), None)

    if not user_data or user_data.get('password') != password:
        return jsonify({'error': 'Invalid credentials'}), 401

    return jsonify({'message': 'Login successful', 'user_data': user_data})

if __name__ == '__main__':
    app.run(debug=True)

# --------------------------- CLASS SCHEDULING ---------------------------
@app.route('/schedule_class', methods=['POST'])
def schedule_class():
    data = request.json
    user_id = data['user_id']
    class_id = data['class_id']
    personalized = data.get('personalized', False)

    if personalized:
        return personalized_class_booking(user_id, class_id)
    else:
        return random_class_booking(user_id, class_id)

# Random (Non-Personalized) Class Booking
def random_class_booking(user_id, class_id):
    class_ref = db.collection('classes').document(class_id)
    class_data = class_ref.get().to_dict()

    if class_data['available_spots'] > 0:
        class_ref.update({'available_spots': class_data['available_spots'] - 1})
        db.collection('bookings').add({'user_id': user_id, 'class_id': class_id})
        return jsonify({'message': 'Class booked successfully'}), 200
    else:
        db.collection('waitlist').add({'user_id': user_id, 'class_id': class_id})
        return jsonify({'message': 'Class full, added to waitlist'}), 400

# Personalized Class Booking
def personalized_class_booking(user_id, class_id):
    user_ref = db.collection('users').document(user_id)
    user_data = user_ref.get().to_dict()
    preferred_time = user_data.get('training_preferences', {}).get('preferred_time', None)

    available_classes = db.collection('classes').where('time', '==', preferred_time).stream()
    best_class = None
    for cls in available_classes:
        cls_data = cls.to_dict()
        if cls_data['available_spots'] > 0:
            best_class = cls
            break

    if best_class:
        best_class.reference.update({'available_spots': best_class.to_dict()['available_spots'] - 1})
        db.collection('bookings').add({'user_id': user_id, 'class_id': best_class.id})
        return jsonify({'message': 'Personalized class booked successfully'}), 200
    else:
        return jsonify({'message': 'No suitable class available'}), 400

# --------------------------- FIND A SPARRING PARTNER ---------------------------
@app.route('/find_partner', methods=['POST'])
def find_partner():
    data = request.json
    user_id = data['user_id']
    personalized = data.get('personalized', False)

    if personalized:
        return personalized_partner_matching(user_id)
    else:
        return random_partner_matching(user_id)

# Random (Non-Personalized) Sparring Partner Matching
def random_partner_matching(user_id):
    available_partners = db.collection('sparring_partners').where('status', '==', 'waiting').stream()
    partners_list = [partner for partner in available_partners]

    if partners_list:
        matched_partner = random.choice(partners_list)
        db.collection('sparring_partners').document(matched_partner.id).update({'status': 'matched', 'partner_id': user_id})
        return jsonify({'message': 'Partner assigned', 'partner_id': matched_partner.id}), 200
    else:
        db.collection('sparring_partners').add({'user_id': user_id, 'status': 'waiting'})
        return jsonify({'message': 'No available partners, added to waiting list'}), 400

# Personalized Sparring Partner Matching
def personalized_partner_matching(user_id):
    user_ref = db.collection('users').document(user_id)
    user_data = user_ref.get().to_dict()
    skill_level = user_data.get('skill_level', 'Beginner')
    preferred_weight_class = user_data.get('training_preferences', {}).get('preferred_weight_class', None)

    matched_partner = None
    query = db.collection('sparring_partners').where('status', '==', 'waiting').where('skill_level', '==', skill_level)
    if preferred_weight_class:
        query = query.where('weight_class', '==', preferred_weight_class)

    partners = query.stream()
    for partner in partners:
        matched_partner = partner
        break

    if matched_partner:
        db.collection('sparring_partners').document(matched_partner.id).update({'status': 'matched', 'partner_id': user_id})
        return jsonify({'message': 'Personalized partner assigned', 'partner_id': matched_partner.id}), 200
    else:
        db.collection('sparring_partners').add({'user_id': user_id, 'skill_level': skill_level, 'weight_class': preferred_weight_class, 'status': 'waiting'})
        return jsonify({'message': 'No suitable partners found, added to waiting list'}), 400

if __name__ == '__main__':
    app.run(debug=True)

