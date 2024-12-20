from sqlite3 import DataError
import fitz  # PyMuPDF
import base64
import json
import requests
import time
import streamlit as st
from dotenv import load_dotenv
import anthropic
import tempfile  # Import tempfile for temporary directories
from langchain_core.tools import Tool
from langchain_google_community import GoogleSearchAPIWrapper
import os, anthropic
import requests
from bs4 import BeautifulSoup
import html2text
import googleapiclient
from urllib.parse import quote


# Load environment variables from .env file
load_dotenv()
api_key = st.secrets["claude_api_key"]
# api_key = os.getenv("claude_api_key")
google_api_key = st.secrets["GOOGLE_API_KEY"]
google_cse_id = st.secrets["GOOGLE_CSE_ID"]

# Initialize OpenAI client
client = anthropic.Anthropic(api_key=api_key)

first_query = """
Please review the provided construction plan document and prepare a comprehensive report that captures the square footage for the following materials and components, only give numarical values. Give the values that accuratly matches the provided context.:

1. Sheetrock 
2. Concrete 
3. Roofing 

For roofing, kindly break down the details for each subtype:
   - Shingle roofing
   - Modified bitumen
   - TPO (Thermoplastic Polyolefin)
   - Metal R panel
   - Standing seam

4. Structural steel

The construction plan may consist of multiple sections or phases. Please make sure the square footage calculations are thorough and include all relevant areas of the document. If there are multiple entries for any material, please combine them to present a total square footage.

Along with the square footage, it would be helpful to include a brief, thoughtful summary of the overall construction plan, highlighting key aspects such as:
   - Materials used
   - Phases of construction outlined
   - Any noteworthy specifications or design elements
   - Location


Ensure the report is detailed, accurate, and provides a complete overview of the square footage calculations and essential aspects of the construction plan.
"""

def fetch_and_process_steel_prices(question: str):
    search = GoogleSearchAPIWrapper(
        google_api_key=google_api_key,
        google_cse_id=google_cse_id,
        k=1
    )

    try:
        print('answer : ', question)
        answer = search.results(question, num_results=5)
        links = [entry['link'] for entry in answer]

        print('answer after search : ',answer)
        def convert_body_to_markdown(url: str):
            try:
                headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
                }
                response = requests.get(url, headers=headers)
                
                # Check if the request was successful (status code 200)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    body = soup.find('body')
                    
                    if body:
                        # Initialize the html2text object
                        h = html2text.HTML2Text()
                        
                        h.ignore_links = True  # Ignore links
                        h.ignore_images = True  # Ignore images
                        
                        # Convert the <body> HTML to Markdown
                        markdown_text = h.handle(str(body))
                        return markdown_text
                    else:
                        # Initialize the html2text object
                        h = html2text.HTML2Text()
                        
                        # h.ignore_links = True  # Ignore links
                        h.ignore_images = True  # Ignore images
                        
                        # Convert the <body> HTML to Markdown
                        markdown_text = h.handle(str(soup))
                        return markdown_text
                
                else:
                    return f"Failed to retrieve the data from the webpage with status code: {response.status_code}"
            
            except Exception as e:
                return f"An error occurred: {str(e)}"

        markdown = ""
        for link in links:
            markdown_content = convert_body_to_markdown(link)
            markdown += f"### Markdown for {link}\n"
            markdown += markdown_content
            markdown += "\n\n"  
            
        client = anthropic.Anthropic(api_key=os.environ.get('claude_api_key'))

        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            system="""You are a Construction Bot with expertise in all aspects of construction, material pricing and related topics. You can analyze and assist with:  
                - Pricing of the materials used in construction.
                - Give all the data for pricing you got from the data.
            """,
            max_tokens=2048,
            messages=[
                {"role": "user", "content": f"{question} {markdown}"}
            ]
        )

        return message.content[0].text

    except googleapiclient.errors.HttpError as e:
        return f"Error during Google Search API request: {str(e)}"



# Function to convert PDF to images
def pdf_to_images(uploaded_file, output_dir):
    pdf_document = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    for i in range(len(pdf_document)):
        page = pdf_document.load_page(i)
        pix = page.get_pixmap()
        img_path = os.path.join(output_dir, f'page_{i}.jpg')
        pix.save(img_path)
    pdf_document.close()

# Function to encode images to Base64
def encode_images(image_directory):
    encoded_images = []
    for filename in os.listdir(image_directory):
        if filename.lower().endswith((".png", ".jpg", ".jpeg")):
            image_path = os.path.join(image_directory, filename)
            with open(image_path, "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
                encoded_images.append(encoded_image)
    return encoded_images



# Function to make chunked API requests and stream combined responses
def chunk_api_requests(encoded_images, user_query, client):
    responses = []  # This will store the responses for each image-query pair
    
    # Loop through each image and make a request to the API
    for i in range(0, len(encoded_images)):
        # time.sleep(1)  # Simulate a delay between requests

        # Create the message structure
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",  # Replace with the appropriate model name
            system="""You are a Construction Bot with expertise in all aspects of construction and related topics. You can analyze and assist with:  
            - Construction plans, blueprints, sketches, and specifications.  
            - Materials selection, quantities, and costs, including concrete, steel, wood, and other building components.  
            - Structural analysis, dimensions, load calculations, and engineering details.  
            - Mechanical, Electrical, and Plumbing (MEP) systems, including HVAC, lighting, and water supply.  
            - Project phases, timelines, and schedules.  
            - Site preparation, drainage, erosion control, and safety systems.  
            - Construction codes, regulations, and standards compliance.  
            - Sustainability practices, green building techniques, and energy-efficient materials.  

            You will only respond to queries related to construction or its associated topics. If asked about anything unrelated to construction, such as food, politics, or general knowledge, respond with: "I am a Construction Bot and can only assist with construction-related topics."
            """,
            max_tokens=2048,
            messages=[  # Sending both the image and text content together
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",  # Specify the encoding type for the image
                                "media_type": "image/jpeg",  # Adjust the image format if necessary
                                "data": encoded_images[i],  # Image data
                            },
                        },
                        {
                            "type": "text",
                            "text": f"""
                            {user_query}
                            """  # The user query associated with the image
                        }
                    ],
                }
            ],
        )

        # Extract the response content
        try:
            # Assuming the message content is in the first element of the response
            response_content = message.content[0].text
            responses.append(response_content)
        except Exception as e:
            # If there is an error, append the error message
            print(f"Error: {str(e)}")
    
    # Combine all the responses into one string
    # combined_responses = "\n\n".join(responses)
    

    final_message = client.messages.create(
        model="claude-3-5-sonnet-20241022",  # Using the same model
        system="""You are a Construction Bot with expertise in all aspects of construction and related topics. You can analyze and assist with:  
            - Construction plans, blueprints, sketches, and specifications.  
            - Materials selection, quantities, and costs, including concrete, steel, wood, and other building components.  
            - Structural analysis, dimensions, load calculations, and engineering details.  
            - Mechanical, Electrical, and Plumbing (MEP) systems, including HVAC, lighting, and water supply.  
            - Project phases, timelines, and schedules.  
            - Site preparation, drainage, erosion control, and safety systems.  
            - Construction codes, regulations, and standards compliance.  
            - Sustainability practices, green building techniques, and energy-efficient materials.  

            You will only respond to queries related to construction or its associated topics. If asked about anything unrelated to construction, such as food, politics, or general knowledge, respond with: "I am a Construction Bot and can only assist with construction-related topics."
            """,
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": f'''Given the following user query and multiple responses, identify and combine the most relevant portions of the responses to provide a comprehensive and informative answer. If the response are like "I am a Construction Bot and can only assist with construction-related topics." infrom the user that I am a Construction Bot and your {user_query} is out of my expertise:

                **User Query:**
                {user_query}

                **Multiple Responses:**
                {responses}

                **Guidelines:**
                * Prioritize accuracy and relevance to the user's query.
                * Combine information from multiple responses if necessary.
                * Avoid redundancy and repetition.
                * Present the information in a clear and concise manner.

                **Output:**
                A single, coherent response that addresses the user's query effectively.
                '''
            }
        ]
    )

    # Print the final response
    return final_message.content[0].text


# Streamlit UI
st.title("PDF Chatbot")

uploaded_file = st.file_uploader("Upload a PDF.", type=["pdf"])

# Initialize session state to manage chat interaction
if 'responses' not in st.session_state:
    st.session_state.responses = []
if 'encoded_images' not in st.session_state:
    st.session_state.encoded_images = []
if 'current_query' not in st.session_state:
    st.session_state.current_query = ""
if 'is_first_query' not in st.session_state:
    st.session_state.is_first_query = True  # Track if it's the first query

# # Chat interaction
if uploaded_file and api_key:
    # Only process the PDF if it hasn't been processed yet
    if not st.session_state.encoded_images:
        with tempfile.TemporaryDirectory() as temp_dir:
            RESULTS_PATH = temp_dir
            
            with st.spinner("Uploading PDF..."):
                # Convert uploaded PDF to images and encode only once
                pdf_to_images(uploaded_file, RESULTS_PATH)
                st.session_state.encoded_images = encode_images(RESULTS_PATH)

    for message in st.session_state.responses:
        with st.chat_message(message['role']):
            st.markdown(message['content'])

    # First predefined query logic
    if st.session_state.is_first_query:
        user_query = first_query
        st.session_state.current_query = user_query

        with st.spinner("Analyzing data..."):
            # Get the combined streamed response
            _f_response = chunk_api_requests(st.session_state.encoded_images, user_query, client)

        with st.chat_message('assistant'):
            st.markdown(_f_response)
        st.session_state.responses.append({"role": "assistant", "content": _f_response})

        st.session_state.is_first_query = False  # After processing the first query
        st.session_state.current_query = ""  # Clear current query after first completion

    # Display chat_input after first query
    toggle_on = st.toggle("Web Search feature", key="web_search_toggle")
    if user_query := st.chat_input("Enter your query"):
        st.session_state.responses.append({"role": "user", "content": user_query})
        
        if toggle_on:
            with st.spinner("Searching the Web..."):
                query = user_query.strip()
                print('query : ', query)
                response = fetch_and_process_steel_prices(query)
        else:
            with st.spinner("Analyzing data..."):
                response = chunk_api_requests(st.session_state.encoded_images, user_query, client)

        with st.chat_message('user'):
            st.markdown(user_query)

        with st.chat_message('assistant'):
            st.markdown(response)
        
        st.session_state.responses.append({"role": "assistant", "content": response})
        st.rerun()  # Trigger rerun after each execution

else:
    st.warning("Please upload a PDF. Uploading PDF might take some time; don't close the application.")
