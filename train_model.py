"""Legal Domain Document Classifier & Relevance Scorer Training Pipeline.

Trains a machine learning model using scikit-learn on legal domain texts.
Produces a serialized pipeline capable of:
1. Classifying legal filings into:
   - Bail Applications (CrPC / BNSS)
   - FIR & Criminal Complaints
   - Police Charge Sheets & Investigation Records
   - Civil Written Statements & Pleadings
   - Legal & Statutory Demand Notices
2. Calculating probabilistic confidence for RAG context routing and reranking.
"""
from pathlib import Path
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


DATA_SAMPLES = [
    # Class: bail_application
    ("The petitioner is quite innocent, poor, vulnerable law abiding person praying for regular bail.", "bail_application"),
    ("Application for grant of anticipatory bail under section 438 CrPC in connection with PS Case.", "bail_application"),
    ("Accused person is ready and willing to furnish solvent surety and abide by any condition imposed by the Hon'ble Court.", "bail_application"),
    ("The applicant has deep roots in society and there is no apprehension of absconding or tampering with evidence.", "bail_application"),
    ("Co-accused has already been enlarged on bail by the Sessions Judge, petitioner seeks parity in bail.", "bail_application"),
    ("Petitioner has been in judicial custody since 45 days, investigation is practically complete, bail prayed.", "bail_application"),
    ("The offences alleged are triable by Magistrate of the First Class and are non-heinous in nature.", "bail_application"),
    ("Petitioner undertakes to cooperate fully with the investigating officer and appear on every date of hearing.", "bail_application"),
    ("No recovery of any incriminating weapon or contraband has been effected from the physical possession of the applicant.", "bail_application"),
    ("Bail application under Section 439 CrPC read with Section 483 BNSS for release of accused on bail bond.", "bail_application"),
    ("It is respectfully prayed that the applicant may be enlarged on bail on furnishing reasonable bail bond.", "bail_application"),
    ("The accused is a senior citizen suffering from chronic ailments requiring regular medical treatment outside jail.", "bail_application"),
    ("Applicant undertakes not to leave the jurisdiction of the court without prior permission during bail.", "bail_application"),
    ("There is no likelihood of the applicant fleeing from justice or intimidating prosecution witnesses.", "bail_application"),
    ("Prayer for grant of pre-arrest bail under section 482 of Bharatiya Nagarik Suraksha Sanhita BNSS.", "bail_application"),
    ("Custodial interrogation of the petitioner is no longer required as chargesheet is already submitted.", "bail_application"),
    ("The applicant was falsely implicated due to previous political rivalry and personal enmity.", "bail_application"),
    ("The petitioner has permanent place of residence at Madhyamgram and shall offer reliable local sureties.", "bail_application"),

    # Class: fir_criminal_complaint
    ("First Information Report registered at Police Station under Sections 498A, 406, 307, 34 of the Indian Penal Code.", "fir_criminal_complaint"),
    ("Complainant states that on 12th March around 9:30 PM the accused persons assaulted the victim with sharp weapons.", "fir_criminal_complaint"),
    ("Complaint lodged by informant alleging criminal breach of trust, cheating, and misappropriation of funds.", "fir_criminal_complaint"),
    ("Incident occurred near the main market where the accused intercepted the vehicle and demanded extortion money.", "fir_criminal_complaint"),
    ("FIR number 142/2024 dated 15-04-2024 registered under Section 420 IPC at Sadar Police Station against named accused.", "fir_criminal_complaint"),
    ("The defacto complainant was subjected to mental and physical cruelty on account of non-fulfillment of dowry demands.", "fir_criminal_complaint"),
    ("Informant submitted written complaint to Officer in Charge regarding theft of motor vehicle from residential parking.", "fir_criminal_complaint"),
    ("Allegations disclose commission of cognizable offence punishable under penal laws warranting registration of case.", "fir_criminal_complaint"),
    ("The victim was immediately shifted to district hospital for emergency medical examination and treatment.", "fir_criminal_complaint"),
    ("Accused persons formed an unlawful assembly armed with deadly weapons and committed criminal trespass.", "fir_criminal_complaint"),
    ("Formal FIR drawn up on basis of written complaint received at the police station reporting theft and robbery.", "fir_criminal_complaint"),
    ("Complainant states that the accused persons threatened with dire consequences and brandished firearm.", "fir_criminal_complaint"),
    ("Case registered under sections 323, 325, 506 IPC upon receiving information from eyewitness at the police outpost.", "fir_criminal_complaint"),
    ("Victim lodged criminal complaint before magistrate alleging dishonestly inducing delivery of valuable property.", "fir_criminal_complaint"),
    ("Details of occurrence: Date of incident 10-01-2024 at 18:00 hours at village square, police complaint recorded.", "fir_criminal_complaint"),
    ("The informant alleges that gold ornaments and cash were looted by unknown miscreants during night burglary.", "fir_criminal_complaint"),

    # Class: chargesheet_police_report
    ("Final Report / Charge Sheet under Section 173 CrPC submitted before the Court of Judicial Magistrate.", "chargesheet_police_report"),
    ("Investigation revealed prima facie evidence against accused person 1 and 2 for commission of offences.", "chargesheet_police_report"),
    ("List of witnesses examined under Section 161 CrPC along with their signed police diary statements.", "chargesheet_police_report"),
    ("Seizure memo and panchnama drawn on spot in presence of independent panch witnesses for seized articles.", "chargesheet_police_report"),
    ("Medical legal case report and injury certificate annexed as prosecution exhibit in the police final form.", "chargesheet_police_report"),
    ("Call detail records and tower location analysis corroborating the presence of the accused at crime scene.", "chargesheet_police_report"),
    ("Malkhana entry register extract and forensic science laboratory ballistic report enclosed with chargesheet.", "chargesheet_police_report"),
    ("Accused is forwarded in custody to stand trial before the competent court of criminal jurisdiction.", "chargesheet_police_report"),
    ("Sanction for prosecution under Section 197 CrPC obtained from competent authority and filed on record.", "chargesheet_police_report"),
    ("Investigation completed and prosecution prays for issuance of process against absconding accused.", "chargesheet_police_report"),
    ("Chargesheet submitted under Section 173(2) CrPC against accused for offences punishable under Section 302 IPC.", "chargesheet_police_report"),
    ("Investigating Officer recorded statement of eyewitnesses and collected circumstantial physical evidence.", "chargesheet_police_report"),
    ("Inquest report under Section 174 CrPC and post mortem examination report tagged with the police docket.", "chargesheet_police_report"),
    ("Forensic chemical examination report confirms presence of human blood matching the blood group of deceased.", "chargesheet_police_report"),
    ("Prosecution list of documents: FIR copy, seizure list, site inspection plan map, and expert opinion report.", "chargesheet_police_report"),
    ("Chargesheet concludes that sufficient oral and documentary evidence exists to put the accused on trial.", "chargesheet_police_report"),

    # Class: written_statement
    ("Written Statement filed on behalf of defendant in response to the civil suit for permanent injunction.", "written_statement"),
    ("The suit is not maintainable either in law or on facts and is barred by principles of res judicata.", "written_statement"),
    ("Defendant specifically denies the averments made in paragraph 4 of the plaint as false and baseless.", "written_statement"),
    ("There is no cause of action accrued in favour of the plaintiff to file and maintain the present suit.", "written_statement"),
    ("The suit has been grossly undervalued and insufficient court fees has been paid by the plaintiff.", "written_statement"),
    ("Preliminary objections: the suit is barred by limitation under Article 54 of the Limitation Act 1963.", "written_statement"),
    ("Plaintiff has suppressed material facts and has not approached the Hon'ble Court with clean hands.", "written_statement"),
    ("The defendant is the absolute, lawful owner in peaceful physical possession of the suit scheduled property.", "written_statement"),
    ("It is therefore prayed that the false, frivolous suit filed by the plaintiff be dismissed with exemplary costs.", "written_statement"),
    ("Verification: I the defendant do hereby verify that the contents of paragraphs 1 to 15 are true to my knowledge.", "written_statement"),
    ("Written statement on behalf of respondent: the allegations in the plaint regarding boundary dispute are denied.", "written_statement"),
    ("The plaintiff has no right, title or interest over the disputed property and has filed a vexatious suit.", "written_statement"),
    ("Defendant submits that the agreement to sell relied upon by plaintiff is forged, fabricated, and unenforceable.", "written_statement"),
    ("Preliminary objection raised that the civil court lacks pecuniary and territorial jurisdiction to try suit.", "written_statement"),
    ("Defendant craves leave to file additional written statement upon production of original documents by plaintiff.", "written_statement"),
    ("The claim of adverse possession made by the plaintiff is untenable in law as defendant is registered title holder.", "written_statement"),

    # Class: legal_notice
    ("Statutory Legal Notice under Section 138 of the Negotiable Instruments Act 1881 for dishonour of cheque.", "legal_notice"),
    ("Notice calling upon you to pay the outstanding balance amount of Rs 15,00,000 within 15 days of receipt.", "legal_notice"),
    ("Cheque issued by you was returned unpaid by the banker with remark 'Funds Insufficient'.", "legal_notice"),
    ("You are hereby called upon to cease and desist from infringing our client's registered trademark rights.", "legal_notice"),
    ("Failure to comply with the demands of this notice within the stipulated statutory period will compel legal action.", "legal_notice"),
    ("Under instructions from and on behalf of our client, we hereby serve you with this formal legal demand notice.", "legal_notice"),
    ("You are liable to compensate our client for damages, mental agony, and legal costs incurred due to your breach.", "legal_notice"),
    ("Take notice that if you fail to remit the sum claimed, criminal proceedings under Section 420 IPC will be initiated.", "legal_notice"),
    ("This notice is issued without prejudice to our client's rights, remedies, and contentions available in law.", "legal_notice"),
    ("Please treat this as a final notice prior to approaching the appropriate court of competent jurisdiction.", "legal_notice"),
    ("Formal legal notice sent through registered post with acknowledgment due regarding breach of contract terms.", "legal_notice"),
    ("Notice of demand calling upon recipient to clear admitted debt with interest at 18 percent per annum.", "legal_notice"),
    ("You are called upon to vacate the tenanted commercial premises within 30 days of service of this notice.", "legal_notice"),
    ("Our client hereby terminates the agreement dated 01-01-2023 on account of material default by your company.", "legal_notice"),
    ("Demand notice: pay the outstanding invoice dues together with costs of this notice within statutory deadline.", "legal_notice"),
    ("Legal notice claiming damages of Rupees Fifty Lakhs for publication of defamatory defamatory material in press.", "legal_notice"),
]


def train_legal_model(output_path: str = "data/models/legal_classifier.joblib"):
    texts = [s[0] for s in DATA_SAMPLES]
    labels = [s[1] for s in DATA_SAMPLES]

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.20, random_state=42, stratify=labels
    )

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2),
            sublinear_tf=True,
            max_features=4000,
            token_pattern=r"(?u)\b[a-zA-Z0-9_\-\.]{2,}\b"
        )),
        ("clf", LogisticRegression(
            C=5.0,
            max_iter=500,
            class_weight="balanced",
            random_state=42
        ))
    ])

    print(f"Training Legal Classifier on {len(texts)} domain samples across 5 classes...")
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"Training complete. Validation Accuracy: {acc * 100:.2f}%")
    print("\nClassification Report:\n", classification_report(y_test, y_pred))

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, out_file)
    print(f"Serialized model saved to: {out_file.resolve()}")

    return pipeline, acc


if __name__ == "__main__":
    train_legal_model()
