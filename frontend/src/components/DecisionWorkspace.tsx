import { CalendarCheck2 } from "lucide-react";

interface DecisionWorkspaceProps {
  crop: string;
  stage: string;
  rainProb: number;
  soilMoisture: number;
  temperature: number;
  result: string;
  onChange: (field: "crop" | "stage" | "rainProb" | "soilMoisture" | "temperature", value: string | number) => void;
  onSubmit: () => void;
}

const crops = ["玉米", "水稻", "小麦", "大豆", "番茄", "黄瓜", "辣椒", "苹果", "柑橘"];
const stages = ["播种出苗期", "苗期", "快速生长期", "开花坐果期", "灌浆成熟期", "采收期"];

export function DecisionWorkspace(props: DecisionWorkspaceProps) {
  const { crop, stage, rainProb, soilMoisture, temperature, result, onChange, onSubmit } = props;

  return (
    <section className="workspace-grid workspace-grid--decision">
      <div className="panel">
        <div className="panel__header">
          <div>
            <h3>田间条件</h3>
            <p>把天气、墒情和生长期作为统一输入，让今天的建议更可执行。</p>
          </div>
        </div>

        <div className="field-grid">
          <label className="field">
            <span>作物</span>
            <div className="field-control field-control--select">
              <select value={crop} onChange={(event) => onChange("crop", event.target.value)}>
                {crops.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
          </label>

          <label className="field">
            <span>生长期</span>
            <div className="field-control field-control--select">
              <select value={stage} onChange={(event) => onChange("stage", event.target.value)}>
                {stages.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
          </label>

          <label className="field">
            <span>气温 ℃</span>
            <div className="field-control">
              <input
                type="number"
                value={temperature}
                min={-20}
                max={55}
                step={0.5}
                onChange={(event) => onChange("temperature", Number(event.target.value))}
              />
            </div>
          </label>

          <label className="field">
            <span>未来降雨概率 {rainProb}%</span>
            <div className="field-control field-control--range">
              <input
                type="range"
                value={rainProb}
                min={0}
                max={100}
                onChange={(event) => onChange("rainProb", Number(event.target.value))}
              />
            </div>
          </label>

          <label className="field">
            <span>土壤湿度 {soilMoisture}%</span>
            <div className="field-control field-control--range">
              <input
                type="range"
                value={soilMoisture}
                min={0}
                max={100}
                onChange={(event) => onChange("soilMoisture", Number(event.target.value))}
              />
            </div>
          </label>
        </div>

        <button className="primary-button" type="button" onClick={onSubmit}>
          <CalendarCheck2 size={16} />
          生成今日建议
        </button>
      </div>

      <div className="panel">
        <div className="panel__header">
          <div>
            <h3>输出结果</h3>
            <p>适合直接给农户说明，也适合留作当天巡田计划。</p>
          </div>
        </div>
        <div className="report-block">{result || "填写条件后，这里会生成建议。"}</div>
      </div>
    </section>
  );
}
