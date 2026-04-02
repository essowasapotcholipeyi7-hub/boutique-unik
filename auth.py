# auth.py
from flask import session, redirect, url_for, flash
from functools import wraps

def login_required(f):
    """Décorateur pour les pages nécessitant une authentification"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Veuillez vous connecter', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def gerant_required(f):
    """Décorateur pour les pages réservées au gérant"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Veuillez vous connecter', 'error')
            return redirect(url_for('login'))
        if session.get('role') != 'gerant':
            flash('Accès réservé au gérant', 'error')
            return redirect(url_for('caisse_index'))
        return f(*args, **kwargs)
    return decorated_function

def vendeur_required(f):
    """Décorateur pour les pages réservées aux vendeurs"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Veuillez vous connecter', 'error')
            return redirect(url_for('login'))
        if session.get('role') not in ['gerant', 'vendeur']:
            flash('Accès non autorisé', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function