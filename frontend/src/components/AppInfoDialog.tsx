import { useRef } from "react";

import { useDialogFocus } from "../hooks/useDialogFocus";
import { formatAppVersion } from "../lib/appVersion";

interface AppInfoDialogProps {
  page: "help" | "about";
  appName: string;
  appVersion: string;
  onClose: () => void;
}

export function AppInfoDialog({ page, appName, appVersion, onClose }: AppInfoDialogProps) {
  const dialog = useRef<HTMLElement>(null);
  useDialogFocus(dialog, true, onClose);

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="confirm-dialog info-dialog"
        ref={dialog}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="app-info-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="ghost-button info-dialog__close" type="button" onClick={onClose}>关闭</button>
        <h3 id="app-info-title">{page === "help" ? "使用帮助" : "关于软件"}</h3>
        {page === "help" ? (
          <>
            <p>注册、登录或使用访客模式后，可以登记地块、记录农事并生成当天农活建议。</p>
            <ul>
              <li>首页和地块卡片可直接记一笔农活，补录日期会重新匹配茬次。费用等可选信息可稍后编辑补全。</li>
              <li>记账失败保留填写内容，请检查网络后重试。未保存离开时可选择继续填写；草稿只在当前页面内，退出或确认放弃后不保留。</li>
              <li>完成待办后可选择顺便记入台账，核对实际日期和内容后保存；取消不会撤销完成。</li>
              <li>地块档案登记面积、土壤和灌溉条件，每块地按茬次记录当季作物。</li>
              <li>结束一茬后可以开始新茬，投入产出按茬次分开算，不混季。</li>
              <li>农事台账按地块记录每次作业的日期、用量、费用，采收还能记产量和单价。</li>
              <li>采收提醒按同一地块全部相关登记施药记录取最晚日期，换茬不会解除未结束的提醒。仅核对登记日期和天数，请以具体产品标签为准。</li>
              <li>农事待办把接下来要做的事排好，逾期会在顶栏标红。</li>
              <li>地块或台账删除后可到回收站恢复；地块关联的茬次、台账和待办一起保留。回收站没有自动清理，最终删除后不能恢复。</li>
              <li>今日农活可选地块带入当季作物。降雨概率、土壤湿度、气温和生长期由你填写或估计，没有自动天气或传感器数据。提示仅按降雨概率和土壤湿度分支，作物、生长期和气温只作记录，不是综合风险评估或用药依据；实际农事请结合现场情况核对。修改任一条件后旧建议清除，须重新生成才能存为待办；保存期间暂不能修改条件。</li>
              <li>每茬收支差额等于已记录收入减已记录支出，不自动包含未登记的人工、地租。费用未填与 0 元分别提示，采收收入仅包含产量和单价均完整的记录。</li>
              <li>统计年度按作业日期划分，跨年茬次只计所选年份；点击金额或待补录数量可追溯台账，返回保留筛选。</li>
              <li>访客可保存为正式账号，原数据保留。演示资料有明确标识，可单独清空；新注册账号默认没有演示资料。</li>
              <li>台账和每茬收支可按当前筛选导出 CSV，包含全部匹配记录。CSV 用于留档和分析，不能作为完整数据库恢复备份。</li>
              <li>显示名称可以随时在个人设置里修改。</li>
              <li>正式账号可在「账号安全」验证原密码后改密，或生成本人离线保管的一次性恢复码。改密或重置会退出全部设备，需重新生成恢复码。</li>
              <li>忘记密码可在登录页使用恢复码；没有恢复码时请联系部署者线下核验身份后辅助恢复，无法核验时不能恢复。访客须先保存账号。</li>
            </ul>
          </>
        ) : (
          <>
            <p>软件全称：{appName}</p>
            <p>软件简称：云寻</p>
            <p>软件版本：{formatAppVersion(appVersion)}</p>
            <p>主要功能：首页、地块与茬次档案、农事台账与待办、每茬已记录收支及追溯、CSV 导出、回收站、账号安全与本机农活建议。</p>
          </>
        )}
      </section>
    </div>
  );
}
