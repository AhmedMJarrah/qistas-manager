"""One deployment, independent manager and reviewer pages."""
from pathlib import Path
import sys
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
pages = [
    st.Page('presentation_app.py', title='عرض شبكة التشريعات', icon=':material/account_tree:', default=True),
    st.Page('volunteer_app.py', title='مهام المتطوعين', icon=':material/fact_check:', url_path='review'),
]
st.navigation(pages).run()
