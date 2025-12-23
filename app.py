from flask import Flask, flash, request, redirect, url_for, render_template, send_file, session
import pandas as pd
import json
import os
import uuid
from extract_txt import read_files
from txt_processing import preprocess
from txt_to_features import txt_features, feats_reduce
from extract_entities import get_number, get_email, rm_email, rm_number, get_name, get_skills
from model import simil 
from werkzeug.security import check_password_hash

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'files\\resumes\\')
DOWNLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'files\\outputs\\')
DATA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Data\\')

for folder in [UPLOAD_FOLDER, DOWNLOAD_FOLDER]:
    if not os.path.isdir(folder):
        os.mkdir(folder)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER
app.config['DATA_FOLDER'] = DATA_FOLDER
app.secret_key = 'nani?!'
ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'doc', 'docx'])

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def _get_files():
    file_list = os.path.join(UPLOAD_FOLDER, 'files.json')
    if os.path.exists(file_list):
        with open(file_list) as fh:
            return json.load(fh)
    return {}

@app.route('/')
def main():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/upload')
def home():
    # if 'username' not in session:
    #     return redirect(url_for('main'))
    return render_template('upload.html') 

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'username' not in session:
        return redirect(url_for('login'))

    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)

    upload_files = request.files.getlist('file')
    if not upload_files:
        flash('No selected file')
        return redirect(request.url)

    for file in upload_files:
        original_filename = file.filename
        if allowed_file(original_filename):
            extension = original_filename.rsplit('.', 1)[1].lower()
            filename = str(uuid.uuid1()) + '.' + extension
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            file_list = os.path.join(UPLOAD_FOLDER, 'files.json')
            files = _get_files()
            files[filename] = original_filename
            with open(file_list, 'w') as fh:
                json.dump(files, fh)

    flash('Upload succeeded')
    return redirect(url_for('home'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        login_path = os.path.join(DATA_FOLDER, 'login_data.xlsx')
        if not os.path.exists(login_path):
            return "Login data file not found."

        df = pd.read_excel(login_path)
        user_row = df[df['username'] == username]

        if not user_row.empty and user_row.iloc[0]['password'] == password:
            session['username'] = username
            return redirect(url_for('main'))
        else:
            flash('Invalid username or password')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('Logged out successfully.')
    return redirect(url_for('login'))

@app.route('/process', methods=["POST"])
def process():
    if 'username' not in session:
        return redirect(url_for('login'))

    try:
        rawtext = request.form['rawtext']
        keywords = [kw.strip().lower() for kw in rawtext.split(",") if kw.strip()]
        if not keywords:
            return "No keywords provided", 400

        jdtxt = [rawtext]
        resumetxt = read_files(UPLOAD_FOLDER)
        p_resumetxt = preprocess(resumetxt)
        p_jdtxt = preprocess(jdtxt)

        feats = txt_features(p_resumetxt, p_jdtxt)
        feats_red = feats_reduce(feats)
        df = simil(feats_red, p_resumetxt, p_jdtxt)

        t = pd.DataFrame({'Original Resume': resumetxt})
        dt = pd.concat([df, t], axis=1)

        dt['Phone No.'] = dt['Original Resume'].apply(get_number)
        dt['E-Mail ID'] = dt['Original Resume'].apply(get_email)

        dt['Original'] = dt['Original Resume'].apply(rm_number).apply(rm_email)
        dt['Candidate\'s Name'] = dt['Original'].apply(get_name)

        skills_list = pd.read_csv(app.config['DATA_FOLDER'] + 'skill_red.csv').values.flatten().tolist()
        skills_list = [z.lower() for z in skills_list]

        dt['Skills'] = dt['Original'].apply(lambda x: get_skills(x, skills_list))

        # Filter: Only resumes that match at least one keyword
        dt = dt[dt['Original'].apply(lambda text: any(kw in text.lower() for kw in keywords))]

        dt = dt.drop(columns=['Original', 'Original Resume'])
        sorted_dt = dt.sort_values(by=['JD 1'], ascending=False)

        out_path = os.path.join(app.config['DOWNLOAD_FOLDER'], "Candidates.csv")
        sorted_dt.to_csv(out_path, index=False)

        table_html = sorted_dt.to_html(classes='table table-striped table-bordered', index=False)
        return render_template('candidates_result.html', table=table_html, download_link='/download/Candidates.csv')

    except Exception as e:
        app.logger.error(f"Error occurred: {e}")
        return f"An error occurred: {str(e)}", 500

@app.route('/candidates', methods=['GET'])
def show_candidates():
    if 'username' not in session:
        return redirect(url_for('login'))

    try:
        # Read all uploaded resumes
        resumetxt = read_files(UPLOAD_FOLDER)
        p_resumetxt = preprocess(resumetxt)

        # Get dummy JD (can be a placeholder)
        p_jdtxt = preprocess(["placeholder jd"])

        feats = txt_features(p_resumetxt, p_jdtxt)
        feats_red = feats_reduce(feats)
        df = simil(feats_red, p_resumetxt, p_jdtxt)

        t = pd.DataFrame({'Original Resume': resumetxt})
        dt = pd.concat([df, t], axis=1)

        dt['Phone No.'] = dt['Original Resume'].apply(get_number)
        dt['E-Mail ID'] = dt['Original Resume'].apply(get_email)

        dt['Original'] = dt['Original Resume'].apply(rm_number).apply(rm_email)
        dt['Candidate\'s Name'] = dt['Original'].apply(get_name)

        skills_list = pd.read_csv(app.config['DATA_FOLDER'] + 'skill_red.csv').values.flatten().tolist()
        skills_list = [z.lower() for z in skills_list]

        dt['Skills'] = dt['Original'].apply(lambda x: get_skills(x, skills_list))

        dt = dt.drop(columns=['Original', 'Original Resume'])
        dt = dt.sort_values(by=['JD 1'], ascending=False)

        table_html = dt.to_html(classes='table table-striped table-bordered', index=False)
        return render_template('candidates.html', table=table_html)

    except Exception as e:
        return f"Error displaying candidates: {str(e)}", 500

@app.route('/download/<code>', methods=['GET'])
def download(code):
    if 'username' not in session:
        return redirect(url_for('login'))

    path = os.path.join(DOWNLOAD_FOLDER, code)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "File not found", 404


if __name__ == "__main__":
    app.run(port=8080, debug=False)
