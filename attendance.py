import streamlit as st
import pandas as pd

st.set_page_config(page_title="근태 분석기 V3", layout="wide")

st.title("📊 2월 근태 이상 내역 자동 분석기 (임원 제외 버전)")

# 1. 제외 대상 성함 설정 (요청하신 성함 반영)
EXCLUDE_NAMES = ['김기돈', '임덕상', '여기대', '김효정', '김운철', '윤희주']
# 부서명이나 성함에 포함될 경우 제외할 키워드
EXCLUDE_KEYWORDS = ['대표', '이사', '본부장'] 

uploaded_file = st.file_uploader("근태 기록 CSV 파일을 업로드하세요", type=['csv'])

if uploaded_file is not None:
    # 인코딩 처리 (Excel 저장 방식에 따라 다를 수 있음)
    try:
        df = pd.read_csv(uploaded_file, encoding='cp949')
    except:
        df = pd.read_csv(uploaded_file, encoding='utf-8-sig')

    # 전처리: 시각 데이터 및 성명 공백 제거
    df['출근시각'] = df['출근시각'].fillna(':').astype(str).str.strip()
    df['퇴근시각'] = df['퇴근시각'].fillna(':').astype(str).str.strip()
    df['성명'] = df['성명'].fillna('').astype(str).str.strip()
    df['부서'] = df['부서'].fillna('').astype(str).str.strip()

    # 결과 분류용 딕셔너리
    results = {
        "출근 누락": [],
        "퇴근 누락": [],
        "연차상신 누락": [],
        "지각(10시 이후)": []
    }

    for _, row in df.iterrows():
        name = row['성명']
        dept = row['부서']
        date = row['근무일자']
        in_t = row['출근시각']
        out_t = row['퇴근시각']

        # [필터링] 제외 대상 성함 및 키워드 체크
        is_excluded = (name in EXCLUDE_NAMES) or \
                      any(k in name for k in EXCLUDE_KEYWORDS) or \
                      any(k in dept for k in EXCLUDE_KEYWORDS)
        
        if is_excluded:
            continue

        # 1. 연차상신 누락 (기록 전무)
        if (in_t in [':', '', 'nan']) and (out_t in [':', '', 'nan']):
            results["연차상신 누락"].append([date, name, dept, in_t, out_t, "기록 없음"])

        # 2. 출근 누락 (퇴근만 있음)
        elif (in_t in [':', '', 'nan']) and (out_t not in [':', '', 'nan']):
            results["출근 누락"].append([date, name, dept, in_t, out_t, "퇴근기록만 존재"])

        # 3. 퇴근 누락 (출근만 있음)
        elif (in_t not in [':', '', 'nan']) and (out_t in [':', '', 'nan']):
            results["퇴근 누락"].append([date, name, dept, in_t, out_t, "출근기록만 존재"])

        # 4. 지각 (10시 01분 이후 출근)
        elif in_t not in [':', '', 'nan']:
            try:
                # '08:26' 같은 형식에서 시, 분 추출
                h, m = map(int, in_t.split(':'))
                if h >= 10 and m > 0:
                    results["지각(10시 이후)"].append([date, name, dept, in_t, out_t, f"{in_t} 출근"])
            except: pass

    # 결과 대시보드 출력
    st.divider()
    cols = st.columns(2)
    summary_for_report = ""

    for i, (category, data) in enumerate(results.items()):
        with cols[i % 2]:
            count = len(data)
            unique_people = len(set([d[1] for d in data]))
            st.subheader(f"📍 {category} ({unique_people}명/{count}건)")
            
            if data:
                res_df = pd.DataFrame(data, columns=['날짜', '성명', '부서', '출근', '퇴근', '비고'])
                st.dataframe(res_df, use_container_width=True)
                
                # 보고서 텍스트 자동 빌드
                names_list = [f"{d[1]}({d[0].split('.')[-1]}일)" for d in data]
                summary_for_report += f"* **{category}** : {unique_people}명/{count}건\n    * {', '.join(names_list)}\n"
            else:
                st.write("이상 내역 없음")

    # 📋 보고서용 텍스트 영역
    st.divider()
    st.subheader("📝 보고서용 요약 텍스트")
    st.text_area("아래 내용을 복사하여 보고서에 붙여넣으세요.", value=summary_for_report, height=200)
