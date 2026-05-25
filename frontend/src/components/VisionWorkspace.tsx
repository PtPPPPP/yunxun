import { ImagePlus, ScanSearch } from "lucide-react";

interface VisionWorkspaceProps {
  previewUrl: string | null;
  crop: string;
  symptom: string;
  result: string;
  modelMode: string;
  aiConfigured: boolean;
  onFileChange: (file: File | null) => void;
  onCropChange: (value: string) => void;
  onSymptomChange: (value: string) => void;
  onSubmit: () => void;
}

const crops = ["玉米", "水稻", "小麦", "大豆", "番茄", "黄瓜", "辣椒", "苹果", "柑橘"];

export function VisionWorkspace(props: VisionWorkspaceProps) {
  const {
    previewUrl,
    crop,
    symptom,
    result,
    modelMode,
    aiConfigured,
    onFileChange,
    onCropChange,
    onSymptomChange,
    onSubmit,
  } = props;

  return (
    <section className="workspace-grid workspace-grid--vision">
      <div className="panel">
        <div className="panel__header">
          <div>
            <h3>上传作物照片</h3>
            <p>浏览器端只把图片传给你自己的后端，不会直接暴露 API Key。</p>
          </div>
        </div>

        <label className="upload-zone">
          <input
            type="file"
            accept="image/png,image/jpeg,image/jpg"
            onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
          />
          {previewUrl ? (
            <img src={previewUrl} alt="作物预览" />
          ) : (
            <div className="upload-zone__empty">
              <ImagePlus size={24} />
              <span>拖拽或选择 JPG / PNG 图片</span>
            </div>
          )}
        </label>
      </div>

      <div className="panel">
        <div className="panel__header">
          <div>
            <h3>诊断信息</h3>
            <p>把作物和现场描述一并带上，模型判断会稳定很多。</p>
          </div>
        </div>

        <div className="field-grid">
          <label className="field">
            <span>作物</span>
            <div className="field-control field-control--select">
              <select value={crop} onChange={(event) => onCropChange(event.target.value)}>
                {crops.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
          </label>

          <label className="field field--full">
            <span>情况描述</span>
            <div className="field-control field-control--textarea">
              <textarea
                value={symptom}
                onChange={(event) => onSymptomChange(event.target.value)}
                placeholder="例如：叶片边缘发黄，最近下过两天雨，出现褐色斑点。"
              />
            </div>
          </label>
        </div>

        <button className="primary-button" type="button" onClick={onSubmit}>
          <ScanSearch size={16} />
          开始诊断
        </button>
      </div>

      <div className="panel panel--full">
        <div className="panel__header">
          <div>
            <h3>诊断结果</h3>
            <p>
              当前为{modelMode}。{aiConfigured ? "会调用已配置的视觉模型。" : "此时不会进行真实图片识别，只返回补拍和排查建议。"}
            </p>
          </div>
        </div>
        <div className="report-block">{result || "上传图片后，这里会显示诊断内容。"}</div>
      </div>
    </section>
  );
}
