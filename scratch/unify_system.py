def update_bundle():
    import subprocess
    content = subprocess.check_output(['git', 'show', 'HEAD:web_dist/assets/index-B7VsJJFA.js']).decode('utf-8')
    text = content

    # 1. Update navs
    old_nav = '["quality","Chất lượng & vận hành",Ps]'
    new_nav = '["system","Hệ thống & Vận hành",kc]'
    assert old_nav in text, 'old_nav not found'
    text = text.replace(old_nav, new_nav, 1)

    # 2. Update pageTitle
    old_title = 'quality:"Chất lượng & vận hành",settings:"Cấu hình không gian làm việc"'
    new_title = 'quality:"Hệ thống & Vận hành",settings:"Hệ thống & Vận hành",system:"Hệ thống & Vận hành"'
    assert old_title in text, 'old_title not found'
    text = text.replace(old_title, new_title, 1)

    # 3. Remove bottom settings link from sidebar
    old_bot = 'l.createElement("a",{href:"#settings",className:u==="settings"?"active":""},l.createElement(kc,{size:18}),"Cài đặt & nguồn dữ liệu"),'
    assert old_bot in text, 'old_bot not found'
    text = text.replace(old_bot, '', 1)

    # 4. Nav active highlight for system
    old_active = 'className:u===f||f==="cases"&&u.startsWith("case/")?"active":""'
    new_active = 'className:(u===f||(f==="cases"&&u.startsWith("case/"))||(f==="system"&&(u==="quality"||u==="settings"||u==="system")))?\"active\":\"\"'
    assert old_active in text, 'old_active not found'
    text = text.replace(old_active, new_active, 1)

    # 5. Route rendering: both quality, settings, system render yh (UnifiedSystemPage)
    old_route = 'u==="quality"&&l.createElement(yh,{run:Te}),u==="settings"&&l.createElement(Eh,{status:s,onRefresh:Ne,onKey:()=>xe(!0)})'
    new_route = '(u==="quality"||u==="settings"||u==="system")&&l.createElement(yh,{route:u,run:Te,status:s,onRefresh:Ne,onKey:()=>xe(!0)})'
    assert old_route in text, 'old_route not found'
    text = text.replace(old_route, new_route, 1)

    # 6. Extract exact q_element and s_element
    m_yh = text.find('function yh({run:u}){')
    end_yh = text.find('function Eh', m_yh)
    end_eh = text.find('Um.createRoot', end_yh)
    assert m_yh != -1 and end_yh != -1 and end_eh != -1

    yh_content = text[m_yh:end_yh]
    eh_content = text[end_yh:end_eh]

    q_idx = yh_content.find('h&&l.createElement(l.Fragment,null,')
    q_call = yh_content[q_idx + len('h&&'):]
    open_p = 0
    q_end_idx = 0
    for i, ch in enumerate(q_call):
        if ch == '(': open_p += 1
        elif ch == ')':
            open_p -= 1
            if open_p == 0:
                q_end_idx = i + 1
                break
    q_element = q_call[:q_end_idx]

    s_start = eh_content.find('l.createElement("section",{className:"card settings-card"}')
    s_call = 'l.createElement(l.Fragment,null,' + eh_content[s_start:]
    open_p = 0
    s_end_idx = 0
    for i, ch in enumerate(s_call):
        if ch == '(': open_p += 1
        elif ch == ')':
            open_p -= 1
            if open_p == 0:
                s_end_idx = i + 1
                break
    s_element = s_call[:s_end_idx]

    new_unified_func = (
        'function yh({route:ro,run:u_run,status:u,onRefresh:onRef,onKey:s}){'
        'var k;'
        'const[tab,setTab]=P.useState(ro==="settings"?"settings":"quality");'
        'const[h,setH]=P.useState(null);'
        'P.useEffect(()=>{if(ro==="settings")setTab("settings");else if(ro==="quality"||ro==="system")setTab("quality");},[ro]);'
        'P.useEffect(()=>{u_run(async()=>setH(await Re("/quality")))},[]);'
        'return l.createElement(l.Fragment,null,'
        'l.createElement("div",{className:"page-heading"},'
        'l.createElement("div",null,'
        'l.createElement("div",{className:"eyebrow"},"HỆ THỐNG & VẬN HÀNH"),'
        'l.createElement("h1",null,"Hệ thống & Vận hành"),'
        'l.createElement("p",null,"Theo dõi chất lượng model, đo lường độ chính xác và cấu hình nguồn dữ liệu.")),'
        'l.createElement("div",{style:{display:"flex",gap:"10px",alignItems:"center"}},'
        'l.createElement(Ge,{value:"unverified"},"Tự động chốt HS8: tắt"),'
        'l.createElement(ke,{icon:ml,onClick:onRef},"Làm mới trạng thái"))),'
        'l.createElement("div",{className:"system-tabs"},'
        'l.createElement("button",{type:"button",className:tab==="quality"?"active":"",onClick:()=>setTab("quality")},"Chất lượng & Đo lường"),'
        'l.createElement("button",{type:"button",className:tab==="settings"?"active":"",onClick:()=>setTab("settings")},"Cấu hình & Nguồn dữ liệu")),'
        'tab==="quality"?(h?' + q_element + ':l.createElement("div",{className:"empty",style:{padding:"40px"}},"Đang tải số liệu chất lượng và vận hành…")):' + s_element + ');}'
    )

    text = text[:m_yh] + new_unified_func + text[end_eh:]

    with open('web_dist/assets/index-B7VsJJFA.js', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Bundle updated successfully with clean system-tabs!")

if __name__ == '__main__':
    update_bundle()
