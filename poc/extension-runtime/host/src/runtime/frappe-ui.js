// The frappe-ui surface extensions may import. Curated rather than `export *`:
// re-exporting the whole library defeats tree-shaking and costs every page
// ~150 kB gzip (measured in this POC). The kit refuses imports outside this list.
export {
  Avatar,
  Badge,
  Button,
  Checkbox,
  Dialog,
  Dropdown,
  FormControl,
  LoadingIndicator,
  Select,
  Switch,
  TabButtons,
  TextInput,
  Textarea,
  Tooltip,
  toast,
  useCall,
} from 'frappe-ui'
