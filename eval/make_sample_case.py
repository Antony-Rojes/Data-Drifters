"""Creates a small FICTIONAL held-out case (3 PDFs) for evaluation and the demo.
All names, places and events are invented. The arrest date deliberately differs between the
arrest memo (12.03.2024) and the remand report (13.03.2024) to test contradiction detection.

Run from the project folder:  python eval/make_sample_case.py
"""
from pathlib import Path

import fitz  # PyMuPDF

OUT = Path(__file__).resolve().parent / "heldout" / "sample_theft_case"

DOCS = {
    "fir_214_2024.pdf": [
        "FIRST INFORMATION REPORT",
        "District: Prayagraj. Police Station: Civil Lines P.S. Year: 2024.",
        "F.I.R. No. 214/2024. Date of FIR: 10.03.2024.",
        "Acts and Sections: Sections 379/411 IPC.",
        "Occurrence of offence: Date of occurrence 08.03.2024 at about 11:30 PM at Shop No. 7, Civil Lines Market, Prayagraj.",
        "Complainant / Informant: Suresh Chand Gupta, son of Late Mohan Lal Gupta, aged 52 years, resident of 22 Kamla Nagar, Prayagraj, shopkeeper by occupation.",
        "Details of known suspect: Ramesh Kumar Yadav, son of Shyam Lal Yadav, aged about 28 years, resident of 14/2 Katra Road, Prayagraj.",
        "Particulars of property stolen: Two mobile phones of Samsung make, total value Rs. 45,000/-.",
        "Statement of the informant: The informant states that on the night of 08.03.2024 he closed his shop at about 10:30 PM. "
        "The next morning he found the shutter lock broken and two mobile phones missing. A neighbouring shopkeeper told him that "
        "he had seen Ramesh Kumar Yadav near the shop late at night.",
        "Action taken: The case is registered and investigation is entrusted to SI Anil Verma.",
    ],
    "arrest_memo.pdf": [
        "ARREST MEMO",
        "Police Station: Civil Lines P.S., District Prayagraj.",
        "Case: F.I.R. No. 214/2024 under Sections 379/411 IPC.",
        "Name of arrested person: Ramesh Kumar Yadav, son of Shyam Lal Yadav, aged 28 years, resident of 14/2 Katra Road, Prayagraj.",
        "Date and time of arrest: The accused was arrested on 12.03.2024 at 6:30 PM near Katra crossing.",
        "Arresting officer: SI Anil Verma, Civil Lines P.S.",
        "Recovery: One Samsung mobile phone was recovered from the possession of the accused.",
        "The grounds of arrest were explained to the arrested person, and his brother Dinesh Yadav was informed of the arrest.",
        "Witness to the arrest: Head Constable Rajpal Singh.",
    ],
    "remand_report.pdf": [
        "POLICE REMAND REPORT",
        "Before the Ld. Chief Judicial Magistrate, Prayagraj.",
        "In re: State vs. Ramesh Kumar Yadav, F.I.R. No. 214/2024, Civil Lines P.S., Sections 379/411 IPC.",
        "1. The accused Ramesh Kumar Yadav was arrested on 13.03.2024 and is produced before the Ld. Court within 24 hours of arrest.",
        "2. One Samsung mobile phone has been recovered. The second mobile phone is yet to be recovered.",
        "3. The accused has no previous criminal record as per the records of this police station.",
        "4. Investigation is in progress. It is prayed that the accused be remanded to judicial custody for 14 days.",
        "Submitted by SI Anil Verma, Investigating Officer, Civil Lines P.S.",
    ],
}


def write_pdf(path, paragraphs):
    pdf = fitz.open()
    page = pdf.new_page()
    y, width = 60, page.rect.width - 120
    for text in paragraphs:
        height = 16 * (len(text) // 85 + 1) + 6
        if y + height > page.rect.height - 60:
            page, y = pdf.new_page(), 60
        page.insert_textbox(fitz.Rect(60, y, 60 + width, y + height), text, fontsize=11, fontname="tiro")
        y += height + 10  # a gap, so each paragraph becomes its own text block (chunk)
    pdf.save(path)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, paragraphs in DOCS.items():
        write_pdf(OUT / name, paragraphs)
        print("written", OUT / name)
