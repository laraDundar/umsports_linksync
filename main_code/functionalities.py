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

# --------------------------- PERSONALISED CLASS SCHEDULING ---------------------------
@app.route('/personalized_schedule', methods=['POST'])
def personalized_schedule():
    data = request.json
    user_id = data['user_id']

    # Get user data
    user_ref = db.collection('users').document(user_id)
    user_data = user_ref.get().to_dict()
    user_cluster_map = cluster_users()
    user_cluster = user_cluster_map.get(user_id, None)

    # Get past attendance
    past_classes = db.collection('registrations').where('user_id', '==', user_id).stream()
    class_frequencies = {}

    for cls in past_classes:
        class_type = cls.to_dict().get('class_type')
        class_frequencies[class_type] = class_frequencies.get(class_type, 0) + 1

    # Get feedback on past sessions
    feedback_ref = db.collection('users').document(user_id).collection('feedback').stream()
    feedback_scores = {}

    for feedback in feedback_ref:
        feedback_data = feedback.to_dict()
        class_type = feedback_data.get('session_id')  # Assuming session_id maps to class type
        avg_score = np.mean(list(feedback_data.values()))
        feedback_scores[class_type] = avg_score

    # Recommend classes based on cluster and training needs
    recommended_classes = []
    cluster_users_ref = db.collection('users').where('cluster', '==', user_cluster).stream()

    for user in cluster_users_ref:
        cluster_user_data = user.to_dict()
        cluster_past_classes = cluster_user_data.get('past_classes', [])
        for cls in cluster_past_classes:
            if cls not in class_frequencies:  # Recommend new classes other cluster users take
                recommended_classes.append(cls)

    # Sort recommendations by least attended but beneficial based on feedback
    sorted_recommendations = sorted(recommended_classes, key=lambda x: feedback_scores.get(x, 0), reverse=True)

    return jsonify({
        'message': 'Personalized class schedule generated',
        'recommended_classes': sorted_recommendations[:3]  # Suggest top 3 new classes
    }), 200

if __name__ == '__main__':
    app.run(debug=True)

# --------------------------- USER CLUSTERING ---------------------------
def cluster_users():
    users = db.collection('users').stream()
    user_vectors = []
    user_ids = []

    for user in users:
        u_data = user.to_dict()
        feedback_scores = np.mean([sum(feedback.values()) / len(feedback) for feedback in u_data.get('feedback', {}).values()]) if u_data.get('feedback') else 0

        vector = [
            u_data.get('skill_level', 1),
            u_data.get('training_frequency', 1),
            feedback_scores,
            len(u_data.get('feedback', {})),
        ]
        user_vectors.append(vector)
        user_ids.append(user.id)

    if len(user_vectors) > 1:
        kmeans = KMeans(n_clusters=min(5, len(user_vectors)), random_state=42).fit(user_vectors)
        clusters = kmeans.labels_
        user_cluster_map = dict(zip(user_ids, clusters))
    else:
        user_cluster_map = {user_ids[0]: 0} if user_ids else {}

    # Store clusters in Firestore
    for user_id, cluster in user_cluster_map.items():
        db.collection('users').document(user_id).update({'cluster': cluster})

    return user_cluster_map

# --------------------------- FIND A SPARRING PARTNER ---------------------------
@app.route('/find_partner', methods=['POST'])
def find_partner():
    data = request.json
    user_id = data['user_id']
    session_id = data['session_id']
    personalized = data.get('personalized', False)

    user_cluster_map = cluster_users()

    if personalized:
        return personalized_partner_matching(user_id, session_id, user_cluster_map)
    else:
        return random_partner_matching(user_id, session_id)

# Random Sparring Partner Matching (30 minutes before session)
def random_partner_matching(user_id, session_id):
    available_partners = db.collection('registrations').where('session_id', '==', session_id).stream()
    partners_list = [partner for partner in available_partners if partner.id != user_id]

    if len(partners_list) >= 3:
        suggested_partners = random.sample(partners_list, 3)
    else:
        suggested_partners = partners_list

    return jsonify({'message': 'Choose a sparring partner', 'suggested_partners': [p.id for p in suggested_partners]}), 200

# Personalized Sparring Partner Matching
def personalized_partner_matching(user_id, session_id, user_cluster_map):
    user_cluster = user_cluster_map.get(user_id, None)
    matched_partners = []

    if user_cluster is not None:
        potential_partners = [u_id for u_id, cluster in user_cluster_map.items() if cluster == user_cluster and u_id != user_id]
        if len(potential_partners) >= 3:
            matched_partners = random.sample(potential_partners, 3)
        else:
            matched_partners = potential_partners

    return jsonify({'message': 'Personalized sparring partners assigned', 'suggested_partners': matched_partners}), 200

    # Collect Feedback After Sparring Session
@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    data = request.json
    user_id = data['user_id']
    partner_id = data['partner_id']
    feedback = data['feedback']  # Dictionary containing answers to 10 feedback questions

    user_ref = db.collection('users').document(user_id)
    partner_ref = db.collection('users').document(partner_id)

    feedback_entry = {
        "partner_id": partner_id,
        "session_id": data.get("session_id"),
        "skill_match": feedback.get("skill_match"),
        "intensity": feedback.get("intensity"),
        "comfort": feedback.get("comfort"),
        "technique_rating": feedback.get("technique_rating"),
        "repeat_preference": feedback.get("repeat_preference"),
        "biggest_struggle": feedback.get("biggest_struggle"),
        "fatigue_level": feedback.get("fatigue_level"),
        "weakness_exposed": feedback.get("weakness_exposed"),
        "training_recommendation": feedback.get("training_recommendation"),
        "cross_training_interest": feedback.get("cross_training_interest"),
        "timestamp": firestore.SERVER_TIMESTAMP
    }

    # Store feedback in Firestore
    db.collection('users').document(user_id).collection('feedback').add(feedback_entry)
    db.collection('users').document(partner_id).collection('received_feedback').add(feedback_entry)

    return jsonify({'message': 'Feedback submitted successfully'}), 200

if __name__ == '__main__':
    app.run(debug=True)


import firebase_admin
from firebase_admin import credentials, db
import re

# Initialize Firebase
cred = credentials.Certificate("path/to/your/firebase-key.json")
firebase_admin.initialize_app(cred, {'databaseURL': 'https://umsports-linksync-default-rtdb.europe-west1.firebasedatabase.app/'})

# Reference to Firebase
ref = db.reference("/")

def move_pending_sessions():
    # Get the pending registrations
    pending_ref = ref.child("login_status/pending_registrations")
    pending_data = pending_ref.get()

    if not pending_data:
        print("No pending registrations found.")
        return

    # Extract user and session details
    match = re.match(r"(\w+)\s(.+)\s-\s([\d:]+)\sto\s([\d:]+)\son\s([\d-]+)", pending_data)

    if match:
        user_id, sport, start_time, end_time, date = match.groups()

        # Define session data
        session_data = {
            "sport": sport,
            "start_time": start_time,
            "end_time": end_time,
            "date": date
        }

        # Update the user's session in `user_registrations`
        user_sessions_ref = ref.child(f"user_registrations/{user_id}/sessions")
        user_sessions_ref.push(session_data)

        # Remove the entry from `pending_registrations`
        pending_ref.delete()

        print(f"✅ Moved session for {user_id} to user_registrations and removed from pending_registrations.")
    else:
        print("❌ Failed to parse session data.")

# Run the function
move_pending_sessions()



