import streamlit as st
import pymysql
import json
from datetime import datetime
from openai import OpenAI
import re
from zoneinfo import ZoneInfo
import fitz  # PyMuPDF
import numpy as np
import os
import hashlib
import time

# ===== Configuration =====
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
MODEL = "gpt-4o"
BASE_DIR = os.path.join(os.getcwd(), "Textbook_2025")
PDF_MAP = {
    "과학2(비상)": ["2025_8th_Sci_V.pdf"],
    "과학3(비상)": ["2025_9th_Sci_V.pdf"],
    "통합과학(동아)": ["2025_10th_Sci_D.pdf"],
    "통합과학(비상)": ["2025_10th_Sci_V.pdf"],
}
SUBJECTS = {
    "중2": ["과학2(비상)"],
    "중3": ["과학3(비상)"],
    "고1": ["통합과학(동아)", "통합과학(비상)"],
}

# Initial prompts
COMMON_PROMPT = (
    "당신은 중고등학생들의 학습을 돕는 AI 튜터입니다.\n"
    "답할 수 없는 정보(시험 범위, 시험 날짜 등)에 대해선 선생님께 문의하도록 안내하세요.\n"
    "따뜻하고 친근한 말투로 존댓말을 사용해 주세요. 학생이 편하게 느낄 수 있도록 상황에 맞는 다양한 이모지, 느낌표 등을 자연스럽게 활용하세요.\n"
    "당신은 학생들이 질문하는 내용에 답하거나, 문제를 내줄 수 있습니다. 학생 수준에 맞게 차근차근 설명해 주세요.\n"
    "당신은 철저하게 교과서 내용에 근거하여 설명과 문항을 제공해야 합니다.\n"
    "모든 수식은 반드시 LaTeX 형식으로 작성하고 '@@@@@'로 감싸주세요. 수식 앞뒤에는 반드시 빈 줄로 구분해 주세요. 이 규칙은 어떤 경우에도 반드시 지켜야 합니다. 예시:\n\n@@@@@\nE_p = 9.8 \\times m \\times h\n@@@@@\n\n"
    "절대로 문장 중간에 LaTeX 형식이 들어가선 안 됩니다. LaTex 사용은 반드시 줄바꿈하고, LaTex 앞뒤를 각각 @ 기호 5개로 감싸야 합니다.\ "
    "틀린 표현 예시: 어떤 물체의 질량이 2kg이고 높이가 10m일 때 위치에너지는((E_p = 9.8 \\times m \\times h))입니다.\n"
    "맞는 표현 예시: 어떤 물체의 질량이 2kg이고 높이가 10m일 때 위치에너지는 다음과 같이 계산할 수 있습니다:\n\n@@@@@\nE_p = 9.8 \\times m \\times h\n@@@@@\n\n"
    "만약 LaTex를 줄바꿈 없이 사용해야만 하는 상황이라면, LaTex가 아닌 글로 쓰세요. \n틀린 표현 예시: 위치에너지는 9.8 \\times m \\times h입니다. \n맞는 표현 예시: 위치에너지는 9.8×m×h입니다. LaTex를 쓰려면 반드시 앞뒤로 줄바꿈해야 합니다.\n"
#    "그림을 출력해야 하는 경우, 링크를 답변에 포함하면 자동으로 그림이 출력됩니다. 따로 하이퍼링크를 만들 필요가 없습니다.\n"
#    "대화 예시: 눈의 구조는 아래 그림을 참고하세요. \n\n https://i.imgur.com/BIFjdBj.png \n"
    "학생이 문제를 내달라고 하면, 어떤 단원 또는 내용에서 문제 내주길 원하는지 물어보세요. 한 번에 여러 개의 문제를 달라는 명시적인 요청이 없다면, 하나의 대화에서는 한 문제만 내세요.\n"
    "만약 학생이 어려운 문제, 난이도 높은 문제를 달라고 한다면, 개인마다 잘 하는 것과 부족한 것이 다르기 때문에 어렵다고 느끼는 문항도 개인별로 다르니 무엇을 잘 하고 못하는지에 대한 파악이 우선되어야 한다고 안내하세요. 내용 자체가 이해되지 않는 것인지, 내용은 이해하지만 문제에 적용하는 것이 어려운 건지, 텍스트·그림·표·그래프 등의 자료 해석이 어려운 건지, 서술형 답을 쓰는 게 어려운 건지 등 무엇을 어렵다고 느끼는 지 상담하며 진단하세요.\n"
    "생성한 응답이 너무 길어지면 학생이 이해하기 어려울 수 있으므로, 가능하면 간결하게 응답하세요.\n"
    "가독성이 좋도록 적절히 줄바꿈으로 하고 개조식으로 답변하세요."
    "풀이 과정이 복잡한 문제에서 답이 부정확한 경우가 종종 있으니, 반드시 Chain-of-Thought 방식으로 단계별로 검토하며 답하세요. 계산 문제나 판단이 필요한 경우, 짧게 쓰더라도 중간 과정이나 이유를 간단히 보여 주세요.\n"
    "학생이 문제를 틀렸는데 맞혔다고 하는 경우가 빈번합니다. 풀이를 먼저 검토하고 정답 여부를 결정하세요.\n"
    "학생이 문제를 틀렸을 경우, 위의 예시와 마찬가지로 한 번에 모든 풀이를 알려주지 말고 순차적으로 질문을 제시하며 학생 스스로 깨달을 수 있게 유도하세요.\n"
    "이미지를 출력거나 웹으로 연결할 때는 링크가 한 글자도 틀려선 안 됩니다. 오탈자 없이 출력하고, 초기 프롬프트에 포함된 링크 외에는 어떠한 링크도 제시하지 마세요.\n"
    "정보 제공을 목적으로 하지 말고, 학생에게 단계적 스캐폴딩을 제공하며 학생 스스로 깨닫도록 하는 것을 목적으로 하세요."
)

SCIENCE_08_PROMPT = (
    "당신은 중학교 2학년 과학 학습 지원을 담당합니다. 아래 1~3을 고려해 학습을 지원하세요. \n"
    "1. 교육과정 성취기준\n"
    "모든 물질은 원소로 이루어져 있음을 이해하고 실험을 통해 원소의 종류를 구별할 수 있다. \n 원자는 원자핵과 전자로 구성됨을 설명할 수 있다. \n 원자와 분자의 개념을 구별하고, 원소와 분자를 원소 기호로 나타낼 수 있다. \n 이온의 형성 과정을 모형과 이온식으로 표현하고, 이온이 전하를 띠고 있음을 설명할 수 있다. \n\n"
    "물체가 대전되는 현상이나 정전기 유도 현상을 관찰하고 그 과정을 전기력과 원자 모형을 이용하여 설명할 수 있다. \n 전기 회로에서 전지의 전압이 전자를 지속적으로 이동하게 하여 전류를 형성함을 모형으로 설명할 수 있다. \n 저항, 전류, 전압 사이의 관계를 실험을 통해 이해하고, 일상생활에서 저항의 직렬연결과 병렬연결의 쓰임새를 조사하여 비교할 수 있다. \n 전류의 자기 작용을 관찰하고 자기장 안에 놓인 전류가 흐르는 코일이 받는 힘을 이용하여 전동기의 원리를 설명할 수 있다. \n\n"
    "지구와 달의 크기를 측정하는 방법을 알고 그 크기를 구할 수 있다. \n 지구 자전에 의한 천체의 겉보기 운동과 지구 공전에 의한 별자리 변화를 설명할 수 있다. \n 달의 위상 변화와 일식과 월식을 설명할 수 있다. \n 태양계를 구성하는 행성의 특징을 알고, 목성형 행성과 지구형 행성으로 구분할 수 있다. \n 태양 표면과 대기의 특징을 알고, 태양의 활동이 지구에 미치는 영향에 대해 설명할 수 있다. \n\n"
    "식물이 생명 활동에 필요한 에너지를 얻기 위해 양분을 만드는 광합성 과정을 이해하고, 광합성에 영향을 미치는 요인을 설명할 수 있다. \n 광합성에 필요한 물의 이동과 증산 작용의 관계를 이해하고, 잎의 증산 작용을 광합성과 관련지어 설명할 수 있다. \n 식물의 호흡을 이해하고, 광합성과의 관계를 설명할 수 있다. \n 광합성 산물의 생성, 저장, 사용 과정을 모형으로 표현할 수 있다. \n\n"
    "생물의 유기적 구성 단계를 설명할 수 있다. \n 음식물이 소화되어 영양소가 흡수되는 과정을 소화 효소의 작용과 관련지어 설명할 수 있다. \n 순환계의 구조와 기능을 이해하고, 혈액의 순환 경로를 나타낼 수 있다. \n 호흡 기관의 구조와 기능을 이해하고, 호흡 운동의 원리를 모형을 사용하여 설명할 수 있다. \n 배설 기관의 구조와 기능을 알고, 노폐물이 배설되는 과정을 표현할 수 있다. \n 동물이 세포 호흡을 통해 에너지를 얻는 과정을 소화, 순환, 호흡, 배설과 관련지어 설명할 수 있다. \n\n"
    "우리 주변에서 볼 수 있는 여러 물질들을 순물질과 혼합물로 구별할 수 있다. \n 밀도, 용해도, 녹는점, 어는점, 끓는점이 물질의 특성이 될 수 있음을 설명할 수 있다. \n 끓는점 차를 이용한 증류의 방법을 이해하고, 우리 주변에서 사용되는 예를 찾아 설명할 수 있다. \n 밀도 차를 이용하여 고체 혼합물 또는 섞이지 않는 액체 혼합물을 분리하는 방법을 이해하고, 우리 주변에서 사용되는 예를 찾아 설명할 수 있다. \n 재결정, 크로마토그래피를 이용한 혼합물 분리 방법을 이해하고, 이를 활용하는 예를 찾아 설명할 수 있다. \n\n"
    "수권에서 해수, 담수, 빙하의 분포와 활용 사례를 조사하고, 자원으로서 물의 가치에 대해 토론할 수 있다. \n 해수의 연직 수온 분포와 염분비 일정 법칙을 통해 해수의 특성을 설명할 수 있다. \n 우리나라 주변 해류의 종류와 특성을 알고 조석 현상에 대한 자료를 해석할 수 있다. \n\n"
    "물체의 온도 차이를 구성 입자의 운동 모형으로 이해하고, 열의 이동 방법과 냉난방 기구의 효율적 사용에 대하여 조사하고 토의할 수 있다. \n 온도가 다른 두 물체가 열평형에 도달하는 과정을 시간-온도 그래프를 이용하여 설명할 수 있다. \n 물질에 따라 비열과 열팽창 정도가 다름을 탐구를 통해 알고, 이를 활용한 예를 설명할 수 있다. \n\n"
    "재해･재난 사례와 관련된 자료를 조사하고, 그 원인과 피해에 대해 과학적으로 분석할 수 있다. \n 과학적 원리를 이용하여 재해･재난에 대한 대처 방안을 세울 수 있다. \n\n"
    "2. 학습 지원 지침\n"
    "학생들의 인지 부하를 고려해, 불가피한 경우를 제외하고는 짧고 간결하며 단계적인 설명을 제공하세요.\n"
    "문제를 낼 때 단순 개념 문제, 개념을 일상생활 상황에 적용해 해석하는 문제, 표를 해석하는 문제, 선택형 문제, 서술형 문제 등을 다양하게 출제하세요.\n"
    "3. 사용 가능한 이미지 목록:\n"
    "이 단원에서는 사용 가능한 이미지가 없습니다. 이미지를 사용하지 마세요. \n"
)

SCIENCE_09_PROMPT = (
    "당신은 중학교 3학년 과학 학습 지원을 담당합니다. 아래 1~3을 고려해 학습을 지원하세요. \n"
    "1. 교육과정 성취기준\n"
    "물리 변화와 화학 변화의 차이를 알고, 일상생활에서 물리 변화와 화학 변화의 예를 찾을 수 있다. \n 간단한 화학 반응을 화학 반응식으로 표현하고, 화학 반응식에서 계수의 비를 입자 수의 비로 해석할 수 있다. \n 질량 보존 법칙을 이해하고, 이를 모형을 사용하여 설명할 수 있다. \n 화합물을 구성하는 성분 원소의 질량에 관한 자료를 해석하여 일정 성분비 법칙을 설명할 수 있다. \n 기체 반응 법칙을 이해하고, 이를 실험을 통해 확인할 수 있다. \n 화학 반응에서 에너지의 출입을 이해하고, 이를 활용한 장치를 설계할 수 있다. \n\n"
    "기권의 층상 구조를 이해하고, 온실 효과와 지구 온난화를 복사 평형의 관점으로 설명할 수 있다. \n 상대 습도, 단열 팽창 및 응결 현상의 관계를 이해하고, 구름의 생성과 강수 과정을 모형으로 표현할 수 있다. \n 기압의 개념을 알고, 바람이 부는 이유를 설명할 수 있다. \n 기단과 전선의 개념을 이해하고, 일기도를 활용하여 저기압과 고기압의 날씨를 비교할 수 있다. \n\n"
    "등속 운동하는 물체의 시간-거리, 시간-속력의 관계를 표현하고 설명할 수 있다. \n 물체의 자유 낙하 운동을 분석하여 시간에 따른 속력의 변화가 일정함을 설명할 수 있다. \n 일의 의미를 알고, 자유 낙하하는 물체의 운동에서 중력이 한 일을 위치 에너지와 운동 에너지로 표현할 수 있다. \n\n"
    "눈, 귀, 코, 혀, 피부 감각기의 구조와 기능을 이해하고 자극의 종류에 따라 감각기를 통해 뇌로 전달되는 과정을 설명할 수 있다. \n 뉴런과 신경계의 구조와 기능을 이해하고 자극에 대한 반응 실험을 통해 자극의 종류에 따라 자극에서 반응이 일어나기까지의 과정을 표현할 수 있다. \n 우리 몸의 기능 조절에 호르몬이 관여함을 알고, 사례를 조사하여 발표할 수 있다. \n\n"
    "세포 분열을 개체의 성장과 관련지어 설명할 수 있다. \n 염색체와 유전자의 관계를 이해하고, 체세포 분열과 생식 세포 형성 과정의 특징을 염색체의 행동을 중심으로 설명할 수 있다. \n 수정란으로부터 개체가 발생되는 과정을 모형으로 표현할 수 있다. \n 멘델 유전 실험의 의의와 원리를 이해하고, 원리가 적용되는 유전 현상을 조사하여 발표할 수 있다. \n 사람의 유전 형질과 유전 연구 방법을 알고, 사람의 유전 현상을 가계도를 이용하여 표현할 수 있다. \n\n"
    "위로 던져 올린 물체와 자유 낙하 물체의 운동에서 위치 에너지와 운동 에너지의 변화를 역학적 에너지 전환과 역학적 에너지 보존으로 예측할 수 있다. \n 자석의 운동에 의해 전류가 발생하는 현상을 관찰하고, 역학적 에너지가 전기 에너지로 전환됨을 설명할 수 있다. \n 가정에서 전기 에너지가 다양한 형태의 에너지로 전환되는 예를 들고, 이를 소비 전력과 관련지어 설명할 수 있다. \n\n"
    "별의 거리를 구하는 방법을 알고, 별의 표면 온도를 색으로 비교할 수 있다. \n 우리은하의 모양, 크기, 구성 천체를 설명할 수 있다. \n 우주가 팽창하고 있음을 모형으로 설명할 수 있다. \n 우주 탐사의 의의와 인류에게 미치는 영향을 조사하여 발표할 수 있다. \n\n"
    "과학기술과 인류 문명의 관계를 이해하고 과학의 유용성에 대해 설명할 수 있다. \n 과학을 활용하여 우리 생활을 보다 편리하게 만드는 방안을 고안하고 그 유용성에 대해 토론할 수 있다. \n\n"
    "2. 학습 지원 지침\n"
    "학생들의 인지 부하를 고려해, 불가피한 경우를 제외하고는 짧고 간결하며 단계적인 설명을 제공하세요.\n"
    "문제를 낼 때 단순 개념 문제, 개념을 일상생활 상황에 적용해 해석하는 문제, 표를 해석하는 문제, 선택형 문제, 서술형 문제 등을 다양하게 출제하세요.\n"
    "3. 사용 가능한 이미지 목록:\n"
    "이 단원에서는 사용 가능한 이미지가 없습니다. 이미지를 사용하지 마세요. \n"
)

SCIENCE_10_PROMPT = (
    "당신은 고등학교 1학년 과학 학습 지원을 담당합니다. 아래 1~3을 고려해 학습을 지원하세요. \n"
    "1. 교육과정 성취기준\n"
    "자연을 시간과 공간에서 기술할 수 있음을 알고, 길이와 시간 측정의 현대적 방법과 다양한 규모의 측정 사례를 조사할 수 있다. \n 과학 탐구에서 중요한 기본량의 의미를 알고, 자연 현상을 기술하는 데 단위가 가지는 의미와 적용사례를 설명할 수 있다. \n 과학 탐구에서 측정과 어림의 의미를 알고, 일상생활의 여러 가지 상황에서 측정 표준의 유용성과 필요성을 논증할 수 있다. \n 자연에서 일어나는 다양한 변화를 측정⋅분석하여 정보를 산출함을 알고, 이러한 정보를 디지털로 변환하는 기술을 정보 통신에 활용하여 현대 문명에 미친 영향을 인식한다. \n\n"
    "천체에서 방출되는 빛의 스펙트럼을 분석하여 우주 초기에 형성된 원소와 천체의 구성 물질을 추론할 수 있다. \n 우주 초기의 원소들로부터 태양계의 재료이면서 생명체를 구성하는 원소들이 형성되는 과정을 통해 지구와 생명의 역사가 우주 역사의 일부분임을 해석할 수 있다. \n 세상을 구성하는 원소들의 성질이 주기성을 나타내는 현상을 통해 자연의 규칙성을 도출하고, 지구와 생명체를 구성하는 주요 원소들이 결합을 형성하는 이유를 해석할 수 있다. \n 인류의 생존에 필수적인 물, 산소, 소금 등이 만들어지는 결합의 차이를 이해하고 각 물질의 성질과 관련지어 설명할 수 있다. \n 지각과 생명체를 구성하는 물질들이 기본 단위체의 결합을 통해서 형성된다는 것을 규산염 광물, 단백질과 핵산의 예를 통해 설명할 수 있다. \n 지구를 구성하는 물질을 전기적 성질에 따라 구분할 수 있고, 물질의 전기적 성질을 응용하여 일상생활과 첨단기술에서 다양한 소재로 활용됨을 인식한다. \n\n"
    "지구시스템은 태양계라는 시스템의 구성요소임을 알고, 지구시스템을 구성하는 권역들 간의 물질 순환과 에너지 흐름의 결과로 나타나는 현상을 논증할 수 있다. \n 지권의 변화를 판구조론 관점에서 해석하고, 에너지 흐름의 결과로 발생하는 지권의 변화가 지구시스템에 미치는 영향을 추론할 수 있다. \n 중력의 작용으로 인한 지구 표면과 지구 주위의 다양한 운동을 설명할 수 있다. \n 상호작용이 없을 때 물체가 가속되지 않음을 알고, 충격량과 운동량의 관계를 충돌 관련 안전장치와 스포츠에 적용할 수 있다. \n 생명 시스템을 유지하기 위해서 다양한 화학 반응과 물질 출입이 필요함을 이해하고, 일상생활에서 활용되는 화학 반응 사례를 조사하여 발표할 수 있다. \n 생명 시스템의 유지에 필요한 세포 내 정보의 흐름을 유전자로부터 단백질이 만들어지는 과정을 중심으로 설명할 수 있다. \n\n"
    "지질시대를 통해 지구 환경이 끊임없이 변화해 왔으며 이러한 환경 변화가 생물다양성에 미치는 영향을 추론할 수 있다. \n 변이의 발생과 자연선택 과정을 통해 생물의 진화가 일어나고, 진화의 과정을 통해 생물다양성이 형성되었음을 추론할 수 있다. \n 자연과 인류의 역사에 큰 변화를 가져온 광합성, 화석 연료 사용, 철의 제련 등에서 공통점을 찾아 산화와 환원을 이해하고, 생활 주변의 다양한 변화를 산화와 환원의 특징과 규칙성으로 분석할 수 있다. \n 대표적인 산⋅염기 물질의 특징을 알고, 산과 염기를 혼합할 때 나타나는 중화 반응을 생활 속에서 이용할 수 있다. \n 생활 주변에서 에너지를 흡수하거나 방출하는 현상을 찾아 에너지의 흡수 방출이 우리 생활에 어떻게 이용되는지 토의할 수 있다. \n\n"
    "생태계 구성요소를 이해하고 생물과 환경 사이의 상호 관계를 설명할 수 있다. \n 먹이 관계와 생태 피라미드를 중심으로 생태계 평형이 유지되는 과정을 이해하고, 환경의 변화가 생태계에 미칠 수 있는 영향에 대해 협력적으로 소통할 수 있다. \n 온실효과 강화로 인한 지구온난화의 메커니즘을 이해하고, 엘니뇨, 사막화 등과 같은 현상이 지구 환경과 인간 생활에 미치는 영향과 대처 방안을 분석할 수 있다. \n 태양에서 수소 핵융합 반응을 통해 질량 일부가 에너지로 바뀌고, 그중 일부가 지구에서 에너지 흐름을 일으키며 다양한 에너지로 전환되는 과정을 추론할 수 있다. \n 발전기에서 운동 에너지가 전기 에너지로 전환되는 과정을 이해하고, 열원으로서 화석 연료, 핵에너지를 이용하는 발전소가 인간 생활에 미치는 영향을 조사⋅발표할 수 있다. \n 에너지 효율의 의미와 중요성을 이해하고, 지속가능한 발전과 지구 환경 문제 해결에 신재생 에너지 기술을 활용하는 방안을 탐색할 수 있다. \n\n"
    "감염병의 진단, 추적 등을 사례로 과학의 유용성을 설명하고, 미래 사회 문제 해결에서 과학의 필요성에 대해 논증할 수 있다. \n 빅데이터를 과학기술사회에서 사용하고 있는 사례를 조사하고, 빅데이터 활용의 장점과 문제점을 추론할 수 있다. \n 인공지능 로봇, 사물인터넷 등과 같이 과학기술의 발전을 인간 삶과 환경 개선에 활용하는 사례를 찾고, 이러한 과학기술의 발전이 미래 사회에 미치는 유용성과 한계를 예측할 수 있다. \n 과학기술의 발전 과정에서 발생할 수 있는 과학 관련 사회적 쟁점(SSI)과 과학기술 이용에서 과학 윤리의 중요성에 대해 논증할 수 있다. \n\n"
    "2. 학습 지원 지침\n"
    "학생들의 인지 부하를 고려해, 불가피한 경우를 제외하고는 짧고 간결하며 단계적인 설명을 제공하세요.\n"
    "문제를 낼 때 단순 개념 문제, 개념을 일상생활 상황에 적용해 해석하는 문제, 표를 해석하는 문제, 선택형 문제, 서술형 문제 등을 다양하게 출제하세요.\n"
    "3. 사용 가능한 이미지 목록:\n"
    "이 단원에서는 사용 가능한 이미지가 없습니다. 이미지를 사용하지 마세요. \n"
)

def summarize_chunks(chunks, unit_prompt, max_chunks=3):
    summaries = []
    for chunk in chunks[:max_chunks]:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": COMMON_PROMPT},
                {"role": "system", "content": unit_prompt},
                {"role": "system",
                 "content": "아래 텍스트를 앞서 언급된 키워드 중심으로 정리해 주세요."},
                {"role": "user",   "content": chunk}
            ]
        )
        summaries.append(resp.choices[0].message.content)
    return "\n\n".join(summaries)

# ===== Helpers =====
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
    text = re.sub(r"\\", "", text)
    text = re.sub(r"\(\((.*?)\)\)", r"\1", text)
    text = re.sub(r"\b(times)\b", "×", text)
    text = re.sub(r"\b(div|divided by)\b", "÷", text)
    text = re.sub(r"\b(plus)\b", "+", text)
    text = re.sub(r"\b(minus)\b", "-", text)
    text = re.sub(r"\^\s*\\circ", "°", text)
    text = re.sub(r"\^circ", "°", text)

    replacements = {
        r"\\perp": "⟂",
        r"\\angle": "∠",
        r"\\parallel": "∥",
        r"\\infty": "∞",
        r"\\approx": "≈",
        r"\\sim": "∼",
        r"\\backsim": "∽",
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

# ===== LLM Router =====
ROUTER_SYS = """너는 중학생의 튜터 라우터다.
사용자 입력과 직전 어시스턴트 메시지를 보고 아래를 JSON으로만 출력한다.

intent:
- "request_problem" : 문제를 내달라는 요청
- "submit_answer"   : 직전 문제에 대한 학생의 답 제출(숫자/기호/짧은 문장 포함)
- "ask_explain"     : 일반 질문/설명 요청 또는 일상 대화

needs_rag:
- true  : 교과서 근거/정의/원문 인용이 필요한 경우(개념 확인·정의·정리·예시 등)
- false : 채점/정오 판정, 단순 계산·추론, 일상 대화처럼 교과서가 없어도 충분한 경우

형식(반드시 JSON만):
{"intent":"request_problem|submit_answer|ask_explain", "needs_rag": true|false, "reason": "한줄 근거"}
"""

def llm_route(user_text: str, last_assistant_msg: str | None) -> dict:
    """
    LLM이 이번 턴의 intent / needs_rag를 판단한다.
    실패 시 ask_explain/needs_rag=True 기본값을 반환(보수적).
    """
    import json, re
    msgs = [
        {"role": "system", "content": ROUTER_SYS},
        {"role": "user", "content":
            f"사용자 입력:\n{user_text}\n\n직전 어시스턴트 메시지(요약 가능):\n{(last_assistant_msg or '없음')[:1200]}"}
    ]
    try:
        r = client.chat.completions.create(model=MODEL, temperature=0, messages=msgs, max_tokens=160)
        raw = r.choices[0].message.content
        m = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(m.group(0)) if m else {}
        if not isinstance(data, dict): raise ValueError("router non-dict")
        data.setdefault("intent", "ask_explain")
        data.setdefault("needs_rag", True)
        return data
    except Exception:
        return {"intent": "ask_explain", "needs_rag": True, "reason": "router_fallback"}

# RAG pipelines
def extract_text_from_pdf(path):
    if not os.path.exists(path):
        return ""
    doc = fitz.open(path)
    return "\n\n".join(page.get_text() for page in doc)

def chunk_text(text, size=1000):
    return [text[i:i+size] for i in range(0, len(text), size)]

def embed_texts(texts):
    if not texts:
        return []
    res = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts
    )
    return [np.array(d.embedding) for d in res.data]

def get_relevant_chunks(question, chunks, embeddings, top_k=3):
    if not chunks:
        return []
    q_emb = np.array(
        client.embeddings.create(
            model="text-embedding-3-small", input=[question]
        ).data[0].embedding
    )
    sims = [np.dot(q_emb, emb)/(np.linalg.norm(q_emb)*np.linalg.norm(emb)) for emb in embeddings]
    idx = np.argsort(sims)[-top_k:][::-1]
    return [chunks[i] for i in idx]

# DB

def connect_to_db():
    return pymysql.connect(
        host=st.secrets["DB_HOST"],
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASSWORD"],
        database=st.secrets["DB_DATABASE"],
        charset="utf8mb4",
        autocommit=True
    )

# === load_chat / save_chat 만 교체 ===

def load_chat(subject, topic):
    name = st.session_state.get("user_name", "").strip()
    code = st.session_state.get("user_code", "").strip()
    grade = subject.strip()
    subject_core = topic.strip()
    if not all([name, code]):
        return []
    try:
        db = connect_to_db(); cur = db.cursor()
        sql = (
            "SELECT chat FROM qna_unique_v4 "
            "WHERE name=%s AND code=%s AND grade=%s AND subject=%s"
        )
        cur.execute(sql, (name, code, grade, subject_core))
        row = cur.fetchone()
        cur.close(); db.close()
        return json.loads(row[0]) if row else []
    except Exception as e:
        st.error(f"DB 오류: {e}")
        return []

def save_chat(subject, topic, chat):
    name = st.session_state.get("user_name", "").strip()
    code = st.session_state.get("user_code", "").strip()
    grade = subject.strip()
    subject_core = topic.strip()
    if not all([name, code]):
        return
    try:
        db = connect_to_db(); cur = db.cursor()
        sql = (
            "INSERT INTO qna_unique_v4 "
            "(name,code,grade,subject,chat,time) VALUES(%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE chat=VALUES(chat), time=VALUES(time)"
        )
        ts = datetime.now(ZoneInfo("Asia/Seoul"))
        cur.execute(sql, (
            name, code, grade, subject_core,
            json.dumps(chat, ensure_ascii=False), ts
        ))
        cur.close(); db.close()
    except Exception as e:
        st.error(f"DB 오류: {e}")

# Spinner 아이콘 정의

def show_stage(message):
    st.markdown(f"""
    <div style='display: flex; align-items: center; font-size: 18px;'>
        <div class="loader" style="
            border: 4px solid #f3f3f3;
            border-top: 4px solid #3498db;
            border-radius: 50%;
            width: 16px;
            height: 16px;
            animation: spin 1s linear infinite;
            margin-right: 10px;
        "></div>
        <div>{message}</div>
    </div>

    <style>
    @keyframes spin {{
        0% {{ transform: rotate(0deg); }}
        100% {{ transform: rotate(360deg); }}
    }}
    </style>
    """, unsafe_allow_html=True)

# Chat UI

def chatbot_tab(subject, topic):
    key = f"chat_{subject}_{topic}".replace(" ", "_")
    load_key = f"loading_{key}"
    input_key = f"buffer_{key}"
    widget_key_base = f"textarea_{key}"

    # 1) 세션 초기화
    if key not in st.session_state:
        st.session_state[key] = load_chat(subject, topic)
    if load_key not in st.session_state:
        st.session_state[load_key] = False
    msgs = st.session_state[key]

    # Select the appropriate science prompt for this unit
    unit_prompts = {
        "과학2(비상)": SCIENCE_08_PROMPT,
        "과학3(비상)": SCIENCE_09_PROMPT,
        "통합과학(동아)": SCIENCE_10_PROMPT,
        "통합과학(비상)": SCIENCE_10_PROMPT,
    }
    selected_unit_prompt = unit_prompts.get(topic, "")

    # 2) 기존 메시지 렌더링
    for msg in msgs:
        if msg["role"] == "user":
            st.write(f"**You:** {msg['content']}")
        else:
            parts = re.split(r"(@@@@@.*?@@@@@)", msg['content'], flags=re.DOTALL)
            for part in parts:
                if part.startswith("@@@@@") and part.endswith("@@@@@"):
                    st.latex(part[5:-5].strip())
                else:
                    txt = clean_inline_latex(part)
                    for link in re.findall(r"(https?://\S+\.(?:png|jpg))", txt):
                        st.image(link)
                        txt = txt.replace(link, "")
                    if txt.strip():
                        st.write(f"**학습 도우미:** {txt.strip()}")

    # 3) 입력창 & 버튼 (토글 방식)
    placeholder = st.empty()
    if not st.session_state[load_key]:
        with placeholder.container():
            user_input = st.text_area("입력:", key=f"{widget_key_base}_{len(msgs)}")
            if st.button("전송", key=f"send_{key}_{len(msgs)}") and user_input.strip():
                st.session_state[input_key] = user_input.strip()
                st.session_state[load_key] = True
                st.rerun()

    # 4) 로딩 상태일 때만 OpenAI 호출 (라우터 → RAG/비RAG 분기)
    if st.session_state[load_key]:
        q = st.session_state.pop(input_key, "")
        if q:
            stage = st.empty()

            # 4-1) 직전 어시스턴트 메시지(문제 출제 여부 등) 확보
            last_assistant_msg = None
            for m in reversed(msgs):
                if m["role"] == "assistant":
                    last_assistant_msg = m["content"]
                    break

            # 4-2) LLM 라우터 호출 (규칙 없이 판단)
            decision = llm_route(q, last_assistant_msg)
            intent = decision.get("intent", "ask_explain")
            use_rag = bool(decision.get("needs_rag", True))

            # 4-3) 공통 시스템 메시지(비RAG/RAG 공통)
            system_messages = [
                {"role": "system", "content": COMMON_PROMPT},
                {"role": "system", "content": selected_unit_prompt},
            ]
            history = [{"role": m["role"], "content": m["content"]} for m in msgs]

            # 4-4) 분기: 비RAG(채점/일상 등) ↔ RAG(교과 근거 필요)
            if not use_rag:
                # ===== 비RAG 경로: 교과서 검색/임베딩 수행 금지 =====
                stage.empty()
                show_stage("답변 생성 중...")

                if intent == "submit_answer":
                    # 채점 전용 프롬프트 (간결)
                    judge_sys = (
                        "당신은 중학생의 튜터 채점관입니다. 학생의 답에 대해 다음 양식으로 답하세요.\n"
                        "1. 풀이 과정 \n\n 2. 판정(정답/오답) \n\n 3. 한 줄 피드백(오개념 교정 또는 학습 조언)\n\n"
                    )

                    prompt = system_messages + [
                        {"role": "system", "content": judge_sys},
                    ] + history + [
                        {"role": "user", "content": f"학생 답: {q}\n상대 대화 맥락을 고려해 채점/피드백만 간단히 제시."}
                    ]
                else:
                    # 일상 대화/가벼운 질문
                    smalltalk_sys = (
                        "당신은 친근한 튜터입니다. 일상 대화/가벼운 질문에는 "
                        "교과서 인용 없이 한두 문장으로 간단히 답합니다."
                    )

                    prompt = system_messages + [
                        {"role": "system", "content": smalltalk_sys},
                    ] + history + [
                        {"role": "user", "content": q}
                    ]

                resp = client.chat.completions.create(model=MODEL, messages=prompt)
                ans = resp.choices[0].message.content

            else:
                # ===== RAG 경로: 이 블록에서만 교과서 검색/임베딩 수행 =====
                stage.empty()
                show_stage("교과서 검색 중...")
                time.sleep(0.5)
                texts = [extract_text_from_pdf(os.path.join(BASE_DIR, fn)) for fn in PDF_MAP[topic]]
                full = "\n\n".join(texts)

                stage.empty()
                show_stage("내용 분석 중...")
                time.sleep(0.5)
                chunks = chunk_text(full)
                embs = embed_texts(chunks)
                relevant = get_relevant_chunks(q, chunks, embs, top_k=3)[:3]

                stage.empty()
                show_stage("답변 생성 중...")
                time.sleep(0.5)
                rag_system_message = {
                    "role": "system",
                    "content": (
                        "아래 청크들은 교과서에서 발췌한 내용입니다. "
                        "질문과 관련된 청크만 참고해 답변하세요. "
                        "답변시 교과서의 표현을 철저하게 반영하세요:\n\n"
                        + "\n\n".join(relevant)
                    ),
                }
                prompt = system_messages + history + [rag_system_message, {"role": "user", "content": q}]
                resp = client.chat.completions.create(model=MODEL, messages=prompt)
                ans = resp.choices[0].message.content

            # 4-5) 공통: 대화 저장 및 리렌더
            stage.empty()
            ts = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")
            msgs.extend(
                [
                    {"role": "user", "content": q, "timestamp": ts},
                    {"role": "assistant", "content": ans},
                ]
            )
            save_chat(subject, topic, msgs)
            st.session_state[key] = msgs
            st.session_state[load_key] = False
            st.rerun()

# ===== Pages =====
def page_1():
    st.title("이곳에 제목을 입력할 수 있습니다(예: 학원명..)")
    st.write("이곳에 내용을 입력할 수 있습니다(예: 간단한 홍보 문구, 연락처..)")
    st.session_state['user_name'] = st.text_input("이름", value=st.session_state.get('user_name',''))
    st.session_state['user_code'] = st.text_input("식별코드", value=st.session_state.get('user_code',''),
        help="타인의 이름으로 접속하는 것을 방지하기 위해 자신만 기억할 수 있는 코드를 입력하세요.")
    st.markdown("> 🌟 “생각하건대 현재의 고난은 장차 우리에게 나타날 영광과 비교할 수 없도다” — 로마서 8장 18절")
    if st.button("다음"):
        if not all([st.session_state['user_name'].strip(), st.session_state['user_code'].strip()]):
            st.error("모든 정보를 입력해주세요.")
        else:
            st.session_state['step']=3; st.rerun()

def page_2(): # 현재 생략되어 있음
    st.title("⚠️모든 대화 내용은 저장되며, 교사가 열람할 수 있습니다.")
    st.write(
       """  
        이 시스템은 학생들을 위한 AI 학습 도우미입니다.
        """)
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("다음"):
            st.session_state["step"] = 3
            st.rerun()

def page_3():
    st.title("과목별 학습")
    st.markdown("❗ AI의 답변은 부정확할 수 있습니다. 의심스러운 정보는 반드시 선생님께 직접 확인하세요.")

    default_subject = "학년을 선택하세요."
    subject = st.selectbox(
        "학년을 선택하세요.",
        [default_subject] + list(SUBJECTS.keys())
    )
    if subject == default_subject:
        return

    default_unit = "과목을 선택하세요."
    units = SUBJECTS[subject]
    unit = st.selectbox(
        "과목을 선택하세요.",
        [default_unit] + units
    )
    if unit == default_unit:
        return

    # 단원이 바뀔 때 세션 상태 초기화
    if "prev_unit" not in st.session_state:
        st.session_state["prev_unit"] = unit

    if unit != st.session_state["prev_unit"]:
        for k in list(st.session_state.keys()):
            if k.startswith("chat_") or k.startswith("buffer_") or k.startswith("loading_") or k.startswith("textarea_"):
                del st.session_state[k]
        st.session_state["prev_unit"] = unit

    chatbot_tab(subject, unit)

# ===== Routing =====
if 'step' not in st.session_state:
    st.session_state['step'] = 1
if st.session_state['step'] == 1:
    page_1()
elif st.session_state['step'] == 2:
    page_2()
else:
    page_3()