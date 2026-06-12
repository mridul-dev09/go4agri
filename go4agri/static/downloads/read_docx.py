import zipfile
import xml.etree.ElementTree as ET

def extract_text_from_docx(docx_path):
    try:
        z = zipfile.ZipFile(docx_path)
        content = z.read('word/document.xml')
        root = ET.fromstring(content)
        # The w:t tags contain the text
        texts = []
        for p in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
            if p.text:
                texts.append(p.text)
        print('\n'.join(texts))
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    extract_text_from_docx('c:/Users/admin/Desktop/go4agri/go4agri/go4agri/uploads/GO4AGRI_Training_Services.docx')
