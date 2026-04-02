# config.py
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-12345'
    DATABASE = os.path.join(os.path.dirname(__file__), 'boutique.db')
    
    # Fuseau horaire GMT (Togo)
    TIMEZONE = 'Africa/Lome'
    
    # Authentification
    MOT_DE_PASSE_GERANT = 'admin123'
    
    # Vendeurs par défaut
    VENDEURS = {
        'Test': {'mdp': 'test123', 'nom': 'Test'},
        'Esther': {'mdp': 'esther123', 'nom': 'Esther'},
        'Shalom': {'mdp': 'shalom123', 'nom': 'Shalom'}
    }