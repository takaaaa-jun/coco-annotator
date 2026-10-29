import axios from "axios";

const baseURL = process.env.BASE_URL + "api/tasks/";

export default {
  all() {
    return axios.get(baseURL);
  },
  delete(id) {
    return axios.delete(baseURL + id);
  },
  getLogs(id) {
    return axios.get(baseURL + id + "/logs");
  }
};
