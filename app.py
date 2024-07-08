from flask import Flask, request, Response, render_template_string, redirect, url_for, session
import yaml
from jinja2 import Environment, FileSystemLoader
import os
import subprocess
from groq import Groq
import json
import secret

app = Flask(__name__)
app.secret_key = secret.session_key  # Needed for session management

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'yaml_data' in request.form:
            yaml_data = request.form['yaml_data']
            session['yaml_data'] = yaml_data  # Store data in session
            return redirect(url_for('process_data'))
        elif 'file' in request.files:
            file = request.files['file']
            yaml_data = yaml.safe_load(file.stream)
            session['yaml_data'] = str(yaml_data)  # Store data in session as a string
            return redirect(url_for('process_data'))
    return render_template_string('''
        <html><body>
        <h2>Enter Your YAML Data</h2>
        <form action="/" method="post">
          <textarea name="yaml_data" cols="100" rows="20"></textarea><br>
          <input type="submit" value="Submit">
          <input type="submit" name="action" value="Download" formaction="/download">
        </form>
        <h2>Or Upload a YAML File</h2>
        <form action="/" method="post" enctype="multipart/form-data">
          <input type="file" name="file">
          <input type="submit" value="Read">
        </form>
        </body></html>
    ''')

@app.route('/download', methods=['POST'])
def download_yaml():
    yaml_data = request.form['yaml_data']
    response = Response(yaml_data, mimetype='text/yaml')
    response.headers['Content-Disposition'] = 'attachment; filename="submitted_data.yaml"'
    return response

@app.route('/process_data', methods=['GET', 'POST'])
def process_data():
    if request.method == 'POST':
        jd = request.form['jd']
        # Store JD in session along with YAML data to maintain state across requests
        session['jd'] = jd
        # Redirect to final_page that will use the data stored in session
        return redirect(url_for('final_page'))

    # Check if YAML data exists in the session and display form for entering JD
    yaml_data = session.get('yaml_data', '')
    if yaml_data == '':
        # If no YAML data in session, redirect to start to ensure flow integrity
        return redirect(url_for('index'))

    return render_template_string('''
        <html><body>
        <h2>Enter Job Description</h2>
        <form action="/process_data" method="post">
          <textarea name="jd" cols="100" rows="10"></textarea><br>
          <button type="submit">Submit JD</button>
        </form>
        </body></html>
    ''')


ct=0
experience_details = {}
def llama_call(data, jd):
    yaml_data = yaml.safe_load(data)
    try:
        if 'experience' in yaml_data:
            for entry in yaml_data["experience"]:
                experience_details[entry["company"]] = entry["details"]

        if 'leadership' in yaml_data:
            for entry in yaml_data['leadership']:
                experience_details[entry["organization"]] = entry["details"]
                
        client = Groq(api_key=secret.api_key) 
        jd_string = "Job Description:\n" + jd
        resume_details = json.dumps(experience_details, indent=2)
        prompt_message = f"""Objective: Generate tailored resume content.
Input Specifications:
- Job Description: Detailed description including required skills and responsibilities.
- Candidate's Basic Experience: Provided as JSON-formatted resume details.

Output Specifications:
- Resume Details Section: Generate targeted bullet points for each company and organization, tailored to the job description. Limit to 3-4 bullet points per company detail.
- Skills Sections: Extract and list technical and soft skills as mentioned in the job description.

Instructions:
Based on the provided job description and candidate's experience and leadership experience, generate a structured JSON output containing tailored resume details for all the sections of resume and relevant skills sections."""

        messages = [
            {"role": "system", "content": prompt_message},
            {"role": "user", "content": f"Job Description:\n{jd}\n\nCandidate's Basic Experience:\n{resume_details}"}
        ]
        completion = client.chat.completions.create(
            model="llama3-70b-8192",
            messages= messages,
            temperature=0.85,
            max_tokens=1830,
            top_p=1,
            stream=False,
            response_format={"type": "json_object"},
            stop=None,
        )
        gen_text = completion.choices[0].message
        json_content = json.loads(gen_text.content)  # Assuming that the output is in JSON string format
        
        if "experience" in yaml_data:
            for section in yaml_data["experience"]:
                company = section['company']
                
                if company in json_content["Resume Details"]:
                    details = json_content["Resume Details"]  # Corrected key access
                    if company in details:  # Check if company exists before accessing details
                        
                        section["details"]=details[company]
            ct+=1
			
        if "leadership" in yaml_data:
            for section in yaml_data["leadership"]:
                    org = section['organization']
                    if org in json_content["Resume Details"]:
                            detail = json_content['Resume Details'][org]
                            if detail and len(detail)>0:
                                section["details"] = detail
                                ct+=1
                                
			
        if "skills" in yaml_data:
          if isinstance(yaml_data, dict):
            yaml_data["skills"] = json_content["Skills"].copy()  # Replace skills with a copy
          else:
            print("Error: resume_details is not a dictionary. Cannot assign skills.")
        else:
              yaml_data["skills"] = json_content["Skills"].copy()  # Add skills with a copy
              ct+=1
   
    except Exception as e:
        print(f"An error occurred: {str(e)}")

    return(yaml_data,ct)



@app.route('/final_page', methods=['GET'])
def final_page():
    yaml_data = session.get('yaml_data', '')
    jd = session.get('jd', '')
    response,ct=llama_call(data=yaml_data,jd=jd)
    if ct == 3:
        show_resume_button = True
    else:
        show_resume_button = False

    return render_template_string('''
        <html><body>
        <h3>YAML Data:</h3>
        <pre>{{ yaml_data }}</pre>
        <h3>Job Description:</h3>
        <pre>{{ jd }}</pre>
        {% if show_resume_button %}
        <a href="/download_resume">Download Resume</a>
        {% endif %}
        </body></html>
    ''', yaml_data=yaml_data, jd=jd, show_resume_button=show_resume_button)

  

if __name__ == '__main__':
    app.run(debug=True)
