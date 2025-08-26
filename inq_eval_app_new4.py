import streamlit as st
import pymysql
import json
import re
import pandas as pd

# ===== LaTeX 텍스트 정리 함수 =====
def clean_inline_latex(text):
    text = re.sub(r",\s*\\text\{(.*?)\}", r" \1", text)
    text = re.sub(r"\\text\{(.*?)\}", r"\1", text)
    text = re.sub(r"\\ce\{(.*?)\}", r"\1", text)
    text = re.sub(r"\\frac\{(.*?)\}\{(.*?)\}", r"\1/\2", text)
    text = re.sub(r"\\sqrt\{(.*?)\}", r"√\1", text)
    text = re.sub(r"\\rightarrow", "→", text)
    text = re.sub(r"\\to", "→", text)
    text = re.sub(r"\^\{(.*?)\}", r"^\1", text)
    text = re.sub(r"_\{(.*?)\}", r"_\1", text)
    text = re.sub(r"\^([0-9])", r"^\1", text)
    text = re.sub(r"_([0-9])", r"\1", text)
    text = re.sub(r"\\", "", text)
    text = re.sub(r"\(\((.*?)\)\)", r"\1", text)
    text = re.sub(r"\(([^()]*\\[a-z]+[^()]*)\)", lambda m: clean_inline_latex(m.group(1)), text)
    text = re.sub(r"\b(times)\b", "×", text)
    text = re.sub(r"\b(div|divided by)\b", "÷", text)
    text = re.sub(r"\b(plus)\b", "+", text)
    text = re.sub(r"\b(minus)\b", "-", text)

    replacements = {
        r"\\perp": "⟂",
        r"\\angle": "∠",
        r"\\parallel": "∥",
        r"\\infty": "∞",
        r"\\approx": "≈",
        r"\\sim": "∼",
        r"\\neq": "≠",
        r"\\leq": "≤",
        r"\\geq": "≥",
        r"\\pm": "±",
        r"\\mp": "∓",
        r"\\cdot": "·",
        r"\\times": "×",
        r"\\div": "÷",
        r"\\propto": "∝",
        r"\\equiv": "≡",
        r"\\cong": "≅",
        r"\\subseteq": "⊆",
        r"\\supseteq": "⊇",
        r"\\subset": "⊂",
        r"\\supset": "⊃",
        r"\\in": "∈",
        r"\\notin": "∉",
        r"\\cup": "∪",
        r"\\cap": "∩",
        r"\\forall": "∀",
        r"\\exists": "∃",
        r"\\nabla": "∇",
        r"\\partial": "∂",
    }
    for pattern, symbol in replacements.items():
        text = re.sub(pattern, symbol, text)

    text = re.sub(r"\bperp\b", "⟂", text)
    text = re.sub(r"\bangle\b", "∠", text)

    return text

# ===== DB 연결 =====
def connect_to_db():
    return pymysql.connect(
        host=st.secrets["DB_HOST"],
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASSWORD"],
        database=st.secrets["DB_DATABASE"],
        charset='utf8mb4'
    )

# ===== 데이터 조회 =====
def fetch_students_v4(grade, subject):
    try:
        db = connect_to_db()
        cursor = db.cursor()
        sql = """
        SELECT DISTINCT name, code
        FROM qna_unique_v4
        WHERE grade = %s AND subject = %s
        ORDER BY number
        """
        cursor.execute(sql, (grade, subject))
        students = cursor.fetchall()
        cursor.close(); db.close()
        return students
    except pymysql.MySQLError as e:
        st.error(f"DB 오류: {e}")
        return []

def fetch_chat_v4(name, code, grade, subject):
    try:
        db = connect_to_db()
        cursor = db.cursor()
        sql = """
        SELECT chat
        FROM qna_unique_v4
        WHERE name = %s AND code = %s AND grade = %s
          AND subject = %s
        """
        cursor.execute(sql, (name, code, grade, subject))
        result = cursor.fetchone()
        cursor.close(); db.close()
        return result[0] if result else None
    except pymysql.MySQLError as e:
        st.error(f"DB 오류: {e}")
        return None

# ===== 삭제 함수 =====
def delete_chat_v4(name, code, grade, subject):
    try:
        db = connect_to_db()
        cursor = db.cursor()
        sql = """
        DELETE FROM qna_unique_v4
        WHERE name = %s AND code = %s AND grade = %s
          AND subject = %s
        """
        cursor.execute(sql, (name, code, grade, subject))
        db.commit()
        cursor.close(); db.close()
        return True
    except pymysql.MySQLError as e:
        st.error(f"삭제 오류: {e}")
        return False

# ===== 기본 UI =====
st.title("학생 AI 대화 이력 조회(개발자용)")
password = st.text_input("비밀번호를 입력하세요", type="password")
if password != st.secrets["PASSWORD"]:
    st.stop()

TOPIC_MAP = {
    "중2": [
        "과학2(비상)"
    ],
    "중3": [
        "과학3(비상)"
    ],
    "고1": [
        "통합과학(동아)",
        "통합과학(비상)"
    ]
}

grade = st.selectbox("학년 선택", ["학년을 선택하세요"] + list(TOPIC_MAP.keys()))
if grade == "학년을 선택하세요":
    st.stop()

subject = st.selectbox("과목 선택", ["과목을 선택하세요"] + TOPIC_MAP.get(grade, []))
if subject == "과목을 선택하세요":
    st.stop()

# ===== 학생 목록 조회 =====
students = fetch_students_v4(grade, subject)
if not students:
    st.warning("해당 과목에 대해 대화한 학생이 없습니다.")
    st.stop()

student_options = [f"{n} / 코드: {c}" for n, c in students]
selected = st.selectbox("학생 선택", student_options)
idx = student_options.index(selected)
name, code = students[idx]

# ===== 대화 불러오기 =====
chat_data = fetch_chat_v4(name, code, grade, subject)
if not chat_data:
    st.warning("대화 기록이 없습니다.")
    st.stop()

# ===== 대화 출력 =====
try:
    chat = json.loads(chat_data)
    st.write("### 대화 내용")
    chat_table = []

    for msg in chat:
        role = "**You:**" if msg["role"] == "user" else "**학습 도우미:**"
        ts = f" ({msg['timestamp']})" if "timestamp" in msg else ""
        content = msg["content"]

        parts = re.split(r"(@@@@@.*?@@@@@)", content, flags=re.DOTALL)
        cleaned_parts = []

        for part in parts:
            if part.startswith("@@@@@") and part.endswith("@@@@@"):
                st.latex(part[5:-5].strip())
                cleaned_parts.append(part[5:-5].strip())
            else:
                txt = clean_inline_latex(part.strip())
                if txt:
                    lines = txt.splitlines()
                    for line in lines:
                        imgs = re.findall(r"(https?://\S+\.(?:png|jpg|jpeg))", line)
                        for img in imgs:
                            st.image(img)
                            line = line.replace(img, "")
                        if line.strip():
                            st.write(f"{role} {line.strip()}{ts}")
                            role = ""  # 한 번만 출력
                    cleaned_parts.append(txt)

        chat_table.append({
            "말한 사람": name if msg["role"] == "user" else "학습 도우미",
            "내용": " ".join(cleaned_parts),
            "시간": msg.get("timestamp", "")
        })

    # ===== 복사용 표 =====
    st.write("### 복사용 표")
    df = pd.DataFrame(chat_table)
    st.markdown(df.to_html(index=False), unsafe_allow_html=True)

except json.JSONDecodeError:
    st.error("대화 JSON 형식 오류입니다.")
    st.stop()

# ===== 삭제 기능 =====
if "delete_confirm" not in st.session_state:
    st.session_state.delete_confirm = False

delete_area = st.empty()

delete_confirm = st.session_state.delete_confirm

if not delete_confirm:
    if delete_area.button("❌ 이 학생의 대화 기록 삭제하기"):
        # 상태 변경 후 rerun → 다음 렌더링에서 확인 버튼 보이게
        st.session_state.delete_confirm = True
        st.rerun()
else:
    st.warning("정말 삭제하시겠습니까? 버튼을 눌러 확정하세요.")
    if delete_area.button("✅ 진짜로 삭제하기"):
        if delete_chat_v4(name, code, grade, subject):
            st.success("삭제 완료")
        else:
            st.error("삭제 실패")
        # 상태 초기화
        st.session_state.delete_confirm = False