from flask import Flask, request, Response,render_template_string, redirect, url_for, session,send_file
import yaml
from jinja2 import Environment, FileSystemLoader
import os
import subprocess
from groq import Groq
import json
import secret
import subprocess
import re


app = Flask(__name__)
app.secret_key = secret.session_key  # Needed for session management

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'yaml_data' in request.form:
            yaml_data = request.form['yaml_data']
            # Instead of storing in session, pass directly to process_data
            return redirect(url_for('process_data', yaml_data=yaml_data))
        elif 'file' in request.files:
            file = request.files['file']
            yaml_data = yaml.safe_load(file.stream)
            # Convert YAML data to a string format that can be passed via URL (careful with size and encoding)
            yaml_data_str = str(yaml_data)
            return redirect(url_for('process_data', yaml_data=yaml_data_str))

    return render_template_string('''
        <html><body>
        <h2>Enter Your YAML Data</h2>
        <form action="/" method="post">
          <textarea name="yaml_data" cols="100" rows="20"></textarea><br>
          <input type="submit" value="Submit">
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
        yaml_data = request.form['yaml_data']
        # Pass JD and YAML data to final_page via URL parameters or by posting directly to the endpoint handling final_page
        return redirect(url_for('final_page', jd=jd, yaml_data=yaml_data))

    # Check if YAML data exists in request arguments and display form for entering JD
    yaml_data = request.args.get('yaml_data', '')
    if yaml_data == '':
        # If no YAML data is available, redirect to start to ensure flow integrity
        return redirect(url_for('index'))

    # Render a form that includes the YAML data as a hidden field
    return render_template_string('''
        <html><body>
        <h2>Enter Job Description</h2>
        <form action="/process_data" method="post">
          <textarea name="jd" cols="100" rows="10"></textarea><br>
          <input type="hidden" name="yaml_data" value="{{ yaml_data }}">
          <button type="submit">Submit JD</button>
        </form>
        </body></html>
    ''', yaml_data=yaml_data)



experience_details = {}
def llama_call(data, jd):
    ct=0
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
        prompt_message = f'''Objective: Generate resume content tailored for job description.
Input Specifications:
- Job Description: Detailed description including required skills and responsibilities.
- Candidate's Basic Experience: Provided as JSON-formatted resume details.

Output Specifications:
- Resume Details: Generate 3-4 tailored bullet points per past role, emphasizing responsibilities and achievements relevant to the job description.
- Skills Section: Identify and list critical technical and soft skills from the job description that align with the candidate's capabilities.

Instructions:
Match Experiences : Align bullet points with the job's required skills and responsibilities, using action verbs and quantitative achievements where possible.
Prioritize Relevant Skills: Extract essential skills from the job description, ensuring they are directly applicable to the position.
Output Format : Ensure JSON output is structured, with clear sections for resume details and skills, categorized under Technical and Soft'''

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
        #print(json_content)
        if "experience" in yaml_data:
            for section in yaml_data["experience"]:
                company = section['company']
                
                if company in json_content["Resume Details"]:
                    details = json_content["Resume Details"]  # Corrected key access
                    if company in details:  # Check if company exists before accessing details
                        
                        section["details"]=details[company]

			
        if "leadership" in yaml_data:
            for section in yaml_data["leadership"]:
                    org = section['organization']
                    if org in json_content["Resume Details"]:
                            detail = json_content['Resume Details'][org]
                            if detail and len(detail)>0:
                                section["details"] = detail
                                
                                
			
        if "skills" in yaml_data:
          if isinstance(yaml_data, dict):
            yaml_data["skills"] = json_content["Skills"].copy()  # Replace skills with a copy
            print("valid")
            ct=1
          else:
            print("Error: resume_details is not a dictionary. Cannot assign skills.")
        else:
              yaml_data["skills"] = json_content["Skills"].copy()
              
              
   
    except Exception as e:
        print(f"An error occurred: {str(e)}")

    return(yaml_data,ct)



@app.route('/final_page', methods=['GET'])
def final_page():
    # Extract data from query parameters instead of the session
    yaml_data = request.args.get('yaml_data', '')
    jd = request.args.get('jd', '')

    # Simulate a function call that processes this data
    response,ct = llama_call(data=yaml_data, jd=jd)

    session["LLM"]=response

    return render_template_string('''
        <html><body>
        <h3>YAML Data:</h3>
        <pre>{{ yaml_data }}</pre>
        <h3>Job Description:</h3>
        <pre>{{ jd }}</pre>
        {% if ct == 1 %}
        <a href="/download_resume">Download Resume</a>
        {% endif %}
        </body></html>
    ''', yaml_data=yaml_data, jd=jd,ct=ct)



def generate_resume(resume):
    env = Environment(
        block_start_string='~<',
        block_end_string='>~',
        variable_start_string='<<',
        variable_end_string='>>',
        comment_start_string='<#',
        comment_end_string='#>',
        trim_blocks=True,
        lstrip_blocks=True,
        loader=FileSystemLoader(searchpath="./"),
    )
    template = env.get_template("resume_template.latex")
    rendered_resume = template.render(resume)
    rendered_resume = rendered_resume.replace("%", "\%")
    print("Type of the resume")
    print(type(rendered_resume))
    filen = resume['name']
    
    output_folder = "output"
    output_filename = f"{filen}_resume.tex"
    output_path = os.path.join(output_folder, output_filename)
    with open(output_path, "w") as fout:
        fout.write(rendered_resume)
    subprocess.run(["pdflatex", f"{filen}_resume.tex"],cwd="./output")
    return output_path
    

@app.route('/download_resume', methods=['GET'])
def download_resume():
    resume_data = session.get("LLM")  # Example session data, replace with actual data
    if not resume_data:
        return "No resume data found!", 404
    pdf_path = generate_resume(resume_data)
    filename = (pdf_path.split("/")[-1]).split(".")[0]
    return send_file(f"output/{filename}.pdf",as_attachment=True)

if __name__ == '__main__':
    
    app.run(debug=True)
