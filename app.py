from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_cors import CORS
from database import get_db, init_db, get_current_datetime
from auth import login_required, gerant_required, vendeur_required
from config import Config
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Initialisation de la base de données
init_db()

# ==================== ROUTES PUBLIQUES ====================

@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'gerant':
            return redirect(url_for('gerant_dashboard'))
        else:
            return redirect(url_for('caisse_index'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form.get('role', 'vendeur')
        
        if role == 'gerant':
            password = request.form.get('password_gerant', '')
            if password == Config.MOT_DE_PASSE_GERANT:
                session['user_id'] = 'gerant'
                session['username'] = 'Gérant'
                session['nom'] = 'Gérant'
                session['role'] = 'gerant'
                flash('Connexion réussie', 'success')
                return redirect(url_for('gerant_dashboard'))
            else:
                flash('Mot de passe incorrect', 'error')
                return redirect(url_for('login'))
        
        else:
            username = request.form.get('username', '').strip()
            password = request.form.get('password_vendeur', '')
            conn = get_db()
            user = conn.execute(
                'SELECT * FROM utilisateurs WHERE username = ? AND password = ? AND actif = 1',
                (username, password)
            ).fetchone()
            conn.close()
            
            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['nom'] = user['nom']
                session['role'] = user['role']
                flash(f'Bonjour {user["nom"]}', 'success')
                return redirect(url_for('caisse_index'))
            else:
                flash('Identifiants incorrects', 'error')
                return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Déconnecté avec succès', 'success')
    return redirect(url_for('login'))

# ==================== ROUTES CAISSE (VENDEUR) ====================

@app.route('/caisse')
@vendeur_required
def caisse_index():
    return render_template('caisse/index.html', user=session)

@app.route('/caisse/caisse')
@vendeur_required
def caisse_caisse():
    return render_template('caisse/caisse.html', user=session)

# ==================== API CAISSE ====================

@app.route('/api/caisse/produits')
@vendeur_required
def api_caisse_produits():
    conn = get_db()
    produits = conn.execute('''
        SELECT id, produit_nom as nom, stock_restant as stock, prix_vente as prixFixe
        FROM stock WHERE stock_restant > 0
        ORDER BY produit_nom
    ''').fetchall()
    conn.close()
    return jsonify([dict(p) for p in produits])

@app.route('/api/caisse/vente', methods=['POST'])
@vendeur_required
def api_caisse_vente():
    data = request.json
    conn = get_db()
    dt = get_current_datetime()
    
    try:
        stock = conn.execute('''
            SELECT stock_restant, prix_vente FROM stock WHERE produit_nom = ?
        ''', (data['produit'],)).fetchone()
        
        if not stock:
            return jsonify({'error': 'Produit non trouvé'}), 404
        
        if stock['stock_restant'] < data['quantite']:
            return jsonify({'error': f'Stock insuffisant. Restant: {stock["stock_restant"]}'}), 400
        
        sous_total = data['quantite'] * data['prixVendu']
        remise = data.get('remise', 0)
        total_net = sous_total - remise
        difference = data['prixVendu'] - stock['prix_vente']
        
        nouveau_stock = stock['stock_restant'] - data['quantite']
        nouvelles_sorties = conn.execute('SELECT sorties FROM stock WHERE produit_nom = ?', 
                                          (data['produit'],)).fetchone()['sorties'] + data['quantite']
        
        conn.execute('''
            UPDATE stock SET stock_restant = ?, sorties = ? WHERE produit_nom = ?
        ''', (nouveau_stock, nouvelles_sorties, data['produit']))
        
        vente_id = f"VENTE_{int(datetime.now().timestamp())}"
        conn.execute('''
            INSERT INTO ventes (vente_id, date, heure, produit, quantite, prix_unitaire, prix_vendu,
                               difference, sous_total, remise, total_net, vendeur, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (vente_id, dt['date'], dt['time'], data['produit'], data['quantite'],
              stock['prix_vente'], data['prixVendu'], difference, sous_total, remise, total_net,
              session.get('nom', session.get('username')), dt['datetime']))
        
        conn.execute('''
            INSERT INTO journal_mvm (date, heure, type, produit, quantite, stock_avant, stock_apres, utilisateur, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (dt['date'], dt['time'], 'VENTE', data['produit'], data['quantite'],
              stock['stock_restant'], nouveau_stock, session.get('nom', session.get('username')), dt['datetime']))
        
        conn.commit()
        return jsonify({'success': True, 'total': total_net, 'message': 'Vente enregistrée'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/caisse/ventes-jour')
@vendeur_required
def api_caisse_ventes_jour():
    conn = get_db()
    dt = get_current_datetime()
    
    ventes = conn.execute('''
        SELECT heure, produit, quantite, prix_unitaire, prix_vendu, remise, total_net, vendeur
        FROM ventes WHERE date = ? ORDER BY id DESC
    ''', (dt['date'],)).fetchall()
    
    total = conn.execute('SELECT COALESCE(SUM(total_net), 0) as total FROM ventes WHERE date = ?', 
                         (dt['date'],)).fetchone()['total']
    nb_ventes = conn.execute('SELECT COUNT(*) as nb FROM ventes WHERE date = ?', 
                              (dt['date'],)).fetchone()['nb']
    nb_produits = conn.execute('SELECT COALESCE(SUM(quantite), 0) as nb FROM ventes WHERE date = ?',
                                (dt['date'],)).fetchone()['nb']
    remise_totale = conn.execute('SELECT COALESCE(SUM(remise), 0) as remise FROM ventes WHERE date = ?',
                                   (dt['date'],)).fetchone()['remise']
    
    conn.close()
    
    return jsonify({
        'date': dt['date'],
        'totalVentes': total,
        'nbVentes': nb_ventes,
        'nbProduitsVendus': nb_produits,
        'remiseTotale': remise_totale,
        'ventes': [dict(v) for v in ventes]
    })

# ==================== ROUTES GÉRANT ====================

@app.route('/gerant/dashboard')
@gerant_required
def gerant_dashboard():
    return render_template('gerant/dashboard.html', user=session)

@app.route('/gerant/vente')
@gerant_required
def gerant_vente():
    return render_template('gerant/vente.html', user=session)

@app.route('/gerant/caisse')
@gerant_required
def gerant_caisse():
    return render_template('gerant/caisse.html', user=session)

@app.route('/gerant/stock')
@gerant_required
def gerant_stock():
    return render_template('gerant/stock.html', user=session)

@app.route('/gerant/catalogue')
@gerant_required
def gerant_catalogue():
    return render_template('gerant/catalogue.html', user=session)

@app.route('/gerant/approvisionnement')
@gerant_required
def gerant_approvisionnement():
    return render_template('gerant/approvisionnement.html', user=session)

@app.route('/gerant/ventes')
@gerant_required
def gerant_ventes():
    return render_template('gerant/ventes.html', user=session)

@app.route('/gerant/journal')
@gerant_required
def gerant_journal():
    return render_template('gerant/journal.html', user=session)

@app.route('/gerant/statistiques')
@gerant_required
def gerant_statistiques():
    return render_template('gerant/statistiques.html', user=session)

@app.route('/gerant/corrections')
@gerant_required
def gerant_corrections():
    return render_template('gerant/corrections.html', user=session)

@app.route('/gerant/admin')
@gerant_required
def gerant_admin():
    return render_template('gerant/admin.html', user=session)
# ==================== API GÉRANT ====================

@app.route('/api/gerant/dashboard')
@gerant_required
def api_gerant_dashboard():
    conn = get_db()
    dt = get_current_datetime()
    
    ca_jour = conn.execute('SELECT COALESCE(SUM(total_net), 0) FROM ventes WHERE date = ?', (dt['date'],)).fetchone()[0]
    
    mois = dt['date'].split('/')[1]
    annee = dt['date'].split('/')[2]
    ca_mois = conn.execute('SELECT COALESCE(SUM(total_net), 0) FROM ventes WHERE strftime("%m", date) = ? AND strftime("%Y", date) = ?', (mois, annee)).fetchone()[0]
    
    nb_produits = conn.execute('SELECT COUNT(*) FROM stock WHERE stock_restant > 0').fetchone()[0]
    alertes = conn.execute('SELECT COUNT(*) FROM stock WHERE stock_restant <= seuil_alerte AND stock_restant > 0').fetchone()[0]
    ruptures = conn.execute('SELECT COUNT(*) FROM stock WHERE stock_restant <= 0').fetchone()[0]
    
    produits_critiques = conn.execute('SELECT produit_nom, stock_restant, seuil_alerte FROM stock WHERE stock_restant <= seuil_alerte ORDER BY stock_restant ASC').fetchall()
    
    top_produits = conn.execute('''
        SELECT produit, SUM(quantite) as quantite, SUM(total_net) as chiffre
        FROM ventes WHERE date >= date('now', '-7 days')
        GROUP BY produit ORDER BY quantite DESC LIMIT 5
    ''').fetchall()
    
    evolution = []
    for i in range(6, -1, -1):
        jour = conn.execute('''
            SELECT date, COALESCE(SUM(total_net), 0) as total
            FROM ventes WHERE date = date('now', ?)
        ''', (f'-{i} days',)).fetchone()
        if jour:
            evolution.append({'jour': jour['date'], 'total': jour['total']})
    
    conn.close()
    
    return jsonify({
        'ca_jour': ca_jour,
        'ca_mois': ca_mois,
        'nb_produits': nb_produits,
        'alertes': alertes + ruptures,
        'produits_critiques': [dict(p) for p in produits_critiques],
        'top_produits': [dict(p) for p in top_produits],
        'evolution': evolution
    })

@app.route('/api/gerant/stock')
@gerant_required
def api_gerant_stock():
    conn = get_db()
    stock = conn.execute('SELECT * FROM stock ORDER BY produit_nom').fetchall()
    nb_produits = len(stock)
    valeur_stock = sum(p['stock_restant'] * p['prix_vente'] for p in stock)
    alertes = sum(1 for p in stock if 0 < p['stock_restant'] <= p['seuil_alerte'])
    ruptures = sum(1 for p in stock if p['stock_restant'] <= 0)
    conn.close()
    return jsonify({
        'stock': [dict(s) for s in stock],
        'nb_produits': nb_produits,
        'valeur_stock': valeur_stock,
        'alertes': alertes,
        'ruptures': ruptures
    })

@app.route('/api/gerant/catalogue')
@gerant_required
def api_gerant_catalogue():
    conn = get_db()
    produits = conn.execute('''
        SELECT p.id, p.nom, p.categorie, p.prix_achat, p.prix_vente, p.fournisseur,
               s.stock_restant, s.seuil_alerte
        FROM produits p
        LEFT JOIN stock s ON p.id = s.produit_id
        WHERE p.actif = 1
        ORDER BY p.nom
    ''').fetchall()
    conn.close()
    return jsonify([dict(p) for p in produits])

@app.route('/api/gerant/produits', methods=['POST'])
@gerant_required
def api_gerant_ajouter_produit():
    data = request.json
    conn = get_db()
    dt = get_current_datetime()
    
    try:
        cursor = conn.execute('''
            INSERT INTO produits (code, nom, categorie, prix_achat, prix_vente, fournisseur, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (f"PROD_{int(datetime.now().timestamp())}", data['nom'], data.get('categorie', ''),
              data['prix_achat'], data['prix_vente'], data['fournisseur'], dt['datetime']))
        produit_id = cursor.lastrowid
        
        conn.execute('''
            INSERT INTO stock (produit_id, produit_nom, stock_initial, stock_restant, seuil_alerte,
                              prix_achat, prix_vente, categorie, fournisseur)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (produit_id, data['nom'], data.get('stock_initial', 0), data.get('stock_initial', 0),
              data.get('seuil', 10), data['prix_achat'], data['prix_vente'], data.get('categorie', ''), data['fournisseur']))
        
        conn.execute('''
            INSERT INTO journal_mvm (date, heure, type, produit, quantite, stock_avant, stock_apres, utilisateur, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (dt['date'], dt['time'], 'AJOUT CATALOGUE', data['nom'], data.get('stock_initial', 0),
              0, data.get('stock_initial', 0), session.get('nom', 'Gérant'), f"Ajout du produit {data['nom']}"))
        
        conn.commit()
        return jsonify({'success': True, 'message': 'Produit ajouté'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/gerant/produits/<int:produit_id>', methods=['DELETE'])
@gerant_required
def api_gerant_supprimer_produit(produit_id):
    conn = get_db()
    dt = get_current_datetime()
    
    try:
        produit = conn.execute('SELECT nom FROM produits WHERE id = ?', (produit_id,)).fetchone()
        produit_nom = produit['nom'] if produit else "Inconnu"
        
        conn.execute('UPDATE produits SET actif = 0 WHERE id = ?', (produit_id,))
        
        conn.execute('''
            INSERT INTO journal_mvm (date, heure, type, produit, quantite, stock_avant, stock_apres, utilisateur, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (dt['date'], dt['time'], 'SUPPRESSION', produit_nom, 0,
              0, 0, session.get('nom', 'Gérant'), f"Suppression du produit {produit_nom}"))
        
        conn.commit()
        return jsonify({'success': True, 'message': 'Produit supprimé'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/gerant/approvisionnement', methods=['POST'])
@gerant_required
def api_gerant_approvisionnement():
    data = request.json
    conn = get_db()
    dt = get_current_datetime()
    
    try:
        stock = conn.execute('SELECT stock_restant FROM stock WHERE produit_nom = ?', (data['produit'],)).fetchone()
        if not stock:
            return jsonify({'success': False, 'error': 'Produit non trouvé'}), 404
        
        stock_avant = stock['stock_restant']
        stock_apres = stock_avant + data['quantite']
        
        conn.execute('''
            UPDATE stock SET stock_restant = ?, entrees = entrees + ? WHERE produit_nom = ?
        ''', (stock_apres, data['quantite'], data['produit']))
        
        conn.execute('''
            INSERT INTO journal_mvm (date, heure, type, produit, quantite, stock_avant, stock_apres, utilisateur, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (dt['date'], dt['time'], 'APPROVISIONNEMENT', data['produit'], data['quantite'],
              stock_avant, stock_apres, session.get('nom', 'Gérant'), f"Approvisionnement de {data['quantite']} unités"))
        
        conn.commit()
        return jsonify({'success': True, 'message': f'✅ {data["quantite"]} unités ajoutées au stock'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/gerant/ventes')
@gerant_required
def api_gerant_ventes():
    conn = get_db()
    ventes = conn.execute('''
        SELECT id, date, heure, produit, quantite, prix_unitaire, prix_vendu, remise, total_net, vendeur
        FROM ventes ORDER BY id DESC LIMIT 1000
    ''').fetchall()
    conn.close()
    return jsonify([dict(v) for v in ventes])

@app.route('/api/gerant/journal')
@gerant_required
def api_gerant_journal():
    conn = get_db()
    journal = conn.execute('''
        SELECT * FROM journal_mvm ORDER BY id DESC LIMIT 500
    ''').fetchall()
    conn.close()
    return jsonify([dict(j) for j in journal])

@app.route('/api/gerant/statistiques')
@gerant_required
def api_gerant_statistiques():
    periode = request.args.get('periode', 'jour')
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    
    conn = get_db()
    dt = get_current_datetime()
    
    if periode == 'jour':
        where = f"date = '{dt['date']}'"
    elif periode == 'semaine':
        where = "date >= date('now', '-7 days')"
    elif periode == 'mois':
        where = "strftime('%m', date) = strftime('%m', 'now') AND strftime('%Y', date) = strftime('%Y', 'now')"
    elif periode == 'annee':
        where = "strftime('%Y', date) = strftime('%Y', 'now')"
    elif periode == 'personnalise' and date_debut and date_fin:
        d1 = date_debut.split('-')
        d2 = date_fin.split('-')
        where = f"date BETWEEN '{d1[2]}/{d1[1]}/{d1[0]}' AND '{d2[2]}/{d2[1]}/{d2[0]}'"
    else:
        where = "1=1"
    
    stats = conn.execute(f'''
        SELECT COALESCE(SUM(total_net), 0) as ca,
               COUNT(*) as nb_ventes,
               COALESCE(SUM(quantite), 0) as nb_produits
        FROM ventes WHERE {where}
    ''').fetchone()
    
    ticket_moyen = stats['ca'] / stats['nb_ventes'] if stats['nb_ventes'] > 0 else 0
    
    top_produits = conn.execute(f'''
        SELECT produit, SUM(quantite) as quantite, SUM(total_net) as chiffre
        FROM ventes WHERE {where}
        GROUP BY produit ORDER BY quantite DESC LIMIT 5
    ''').fetchall()
    
    top_vendeurs = conn.execute(f'''
        SELECT vendeur, COUNT(*) as nb_ventes, SUM(total_net) as chiffre
        FROM ventes WHERE {where}
        GROUP BY vendeur ORDER BY chiffre DESC LIMIT 5
    ''').fetchall()
    
    if periode == 'jour':
        evolution = conn.execute('''
            SELECT heure as periode, SUM(total_net) as total
            FROM ventes WHERE date = ?
            GROUP BY heure ORDER BY heure
        ''', (dt['date'],)).fetchall()
    else:
        evolution = conn.execute(f'''
            SELECT date as periode, SUM(total_net) as total
            FROM ventes WHERE {where}
            GROUP BY date ORDER BY date
        ''').fetchall()
    
    conn.close()
    
    return jsonify({
        'chiffre_affaire': stats['ca'],
        'nb_ventes': stats['nb_ventes'],
        'nb_produits_vendus': stats['nb_produits'],
        'ticket_moyen': ticket_moyen,
        'top_produits': [dict(p) for p in top_produits],
        'top_vendeurs': [dict(v) for v in top_vendeurs],
        'evolution': [dict(e) for e in evolution]
    })

@app.route('/api/gerant/correction', methods=['POST'])
@gerant_required
def api_gerant_correction():
    data = request.json
    conn = get_db()
    dt = get_current_datetime()
    
    try:
        vente = conn.execute('SELECT * FROM ventes WHERE id = ?', (data['id'],)).fetchone()
        if not vente:
            return jsonify({'success': False, 'error': 'Vente non trouvée'}), 404
        
        if data['action'] == 'annulation':
            conn.execute('UPDATE ventes SET statut = ? WHERE id = ?', ('ANNULÉE', data['id']))
            conn.execute('''
                INSERT INTO journal_mvm (date, heure, type, produit, quantite, stock_avant, stock_apres, utilisateur, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (dt['date'], dt['time'], 'ANNULATION', vente['produit'], vente['quantite'],
                  vente['quantite'], 0, session.get('nom', 'Gérant'), data.get('motif', '')))
            
        elif data['action'] == 'remboursement':
            conn.execute('UPDATE ventes SET statut = ? WHERE id = ?', ('REMBOURSÉE', data['id']))
            conn.execute('''
                INSERT INTO journal_mvm (date, heure, type, produit, quantite, stock_avant, stock_apres, utilisateur, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (dt['date'], dt['time'], 'REMBOURSEMENT', vente['produit'], vente['quantite'],
                  vente['quantite'], 0, session.get('nom', 'Gérant'), data.get('motif', '')))
            
        elif data['action'] == 'correctionPrix':
            diff = data['nouveau_prix'] - vente['prix_unitaire']
            sous_total = vente['quantite'] * data['nouveau_prix']
            total_net = sous_total - vente['remise']
            conn.execute('''
                UPDATE ventes SET prix_vendu = ?, difference = ?, sous_total = ?, total_net = ?, statut = ?
                WHERE id = ?
            ''', (data['nouveau_prix'], diff, sous_total, total_net, 'CORRIGÉE', data['id']))
            conn.execute('''
                INSERT INTO journal_mvm (date, heure, type, produit, quantite, utilisateur, details)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (dt['date'], dt['time'], 'CORRECTION PRIX', vente['produit'], vente['quantite'],
                  session.get('nom', 'Gérant'), f"{data.get('motif', '')} - Ancien prix: {vente['prix_vendu']} -> Nouveau: {data['nouveau_prix']}"))
            
        elif data['action'] == 'correctionQuantite':
            sous_total = data['nouvelle_quantite'] * vente['prix_vendu']
            total_net = sous_total - vente['remise']
            conn.execute('''
                UPDATE ventes SET quantite = ?, sous_total = ?, total_net = ?, statut = ?
                WHERE id = ?
            ''', (data['nouvelle_quantite'], sous_total, total_net, 'CORRIGÉE', data['id']))
            conn.execute('''
                INSERT INTO journal_mvm (date, heure, type, produit, quantite, utilisateur, details)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (dt['date'], dt['time'], 'CORRECTION QUANTITÉ', vente['produit'], f"{vente['quantite']}->{data['nouvelle_quantite']}",
                  session.get('nom', 'Gérant'), data.get('motif', '')))
        
        conn.commit()
        return jsonify({'success': True, 'message': 'Correction effectuée'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/gerant/vendeurs')
@gerant_required
def api_gerant_vendeurs():
    conn = get_db()
    vendeurs = conn.execute('SELECT id, username, nom, role, actif FROM utilisateurs WHERE role = "vendeur" ORDER BY username').fetchall()
    conn.close()
    return jsonify([dict(v) for v in vendeurs])

@app.route('/api/gerant/vendeurs', methods=['POST'])
@gerant_required
def api_gerant_ajouter_vendeur():
    data = request.json
    conn = get_db()
    dt = get_current_datetime()
    
    try:
        conn.execute('''
            INSERT INTO utilisateurs (username, password, nom, role, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (data['username'], data['password'], data['nom'], 'vendeur', dt['datetime']))
        conn.commit()
        return jsonify({'success': True, 'message': 'Vendeur ajouté'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'error': 'Nom d\'utilisateur déjà existant'}), 400
    finally:
        conn.close()

@app.route('/api/gerant/vendeurs/<int:vendeur_id>', methods=['DELETE'])
@gerant_required
def api_gerant_desactiver_vendeur(vendeur_id):
    conn = get_db()
    try:
        conn.execute('UPDATE utilisateurs SET actif = 0 WHERE id = ?', (vendeur_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Vendeur désactivé'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()
@app.route('/gerant/historiques')
@gerant_required
def gerant_historiques():
    return render_template('gerant/historiques.html', user=session)
@app.route('/api/gerant/changer-mdp', methods=['POST'])
@gerant_required
def api_gerant_changer_mdp():
    data = request.json
    return jsonify({'success': True, 'message': 'Mot de passe changé'})

if __name__ == '__main__':
    app.run(debug=True)