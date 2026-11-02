"""Compatibility launcher. The maintained user interface is served by FastAPI."""
import os
import streamlit as st
st.set_page_config(page_title='HS Workspace',page_icon='📁',layout='centered')
st.title('HS Workspace 2.0')
st.write('Ứng dụng đã chuyển sang giao diện hồ sơ và từng SKU, có kiểm tra thuộc tính, căn cứ và bước duyệt.')
st.code('python -m pip install -r requirements.txt\npython serve.py',language='bash')
st.link_button('Mở giao diện HS Workspace',os.environ.get('HS_WORKSPACE_URL','http://127.0.0.1:8000'))
st.caption('Bản Streamlit cũ được giữ trong legacy để tham khảo. Dùng giao diện mới để có đầy đủ kiểm tra nghiệp vụ.')
